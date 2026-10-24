// Local HTTPS acceptance only. No OS certificate installation or production services.
import { spawn, execFileSync } from "node:child_process";
import {
  mkdtempSync,
  readFileSync,
  writeFileSync,
  rmSync,
  existsSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { resolve, join } from "node:path";
import { createServer } from "node:net";
import https from "node:https";

const root = resolve(import.meta.dirname, "..");
const server = resolve(root, "../server");
const python = join(server, ".venv/bin/python");
const caddy = process.env.CADDY_BIN || "caddy";
execFileSync(caddy, ["version"], { stdio: "inherit" });
for (const role of ["parent", "student"]) {
  if (!existsSync(join(root, "dist", role, "index.html")))
    throw new Error("Build both roles first.");
}
for (const port of [8810, 18443, 19443, 18811]) {
  await new Promise((resolve, reject) => {
    const check = createServer();
    check.once("error", reject);
    check.listen(port, "127.0.0.1", () => check.close(resolve));
  });
}
const runtime = mkdtempSync(join(tmpdir(), "ai-web-https-"));
const children = [];
let stopping = false;
async function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  await Promise.all(
    children.map(
      (child) =>
        new Promise((resolve) => {
          if (child.exitCode !== null || child.signalCode !== null)
            return resolve();
          const timer = setTimeout(() => {
            child.kill("SIGKILL");
            resolve();
          }, 5000);
          child.once("exit", () => {
            clearTimeout(timer);
            resolve();
          });
          child.kill("SIGTERM");
        }),
    ),
  );
  rmSync(runtime, { recursive: true, force: true });
  process.exit(code);
}
process.on("SIGTERM", () => stop());
process.on("SIGINT", () => stop());
process.on("uncaughtException", (error) => {
  console.error(error);
  stop(1);
});
process.on("unhandledRejection", (error) => {
  console.error(error);
  stop(1);
});

execFileSync(
  python,
  [
    "-c",
    String.raw`
import sys, ipaddress
from pathlib import Path
from datetime import datetime, timedelta, timezone
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
root = Path(sys.argv[1])
now = datetime.now(timezone.utc)
ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'AI StudyNest temporary test CA')])
ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key())
      .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1))
      .not_valid_after(now+timedelta(days=1)).add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
      .sign(ca_key, hashes.SHA256()))
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
cert = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')]))
        .issuer_name(ca_name).public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost'), x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]), critical=False)
        .sign(ca_key, hashes.SHA256()))
(root/'ca.pem').write_bytes(ca.public_bytes(serialization.Encoding.PEM))
(root/'cert.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
(root/'key.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
(root/'key.pem').chmod(0o600)
`,
    runtime,
  ],
  { cwd: server, stdio: "inherit" },
);

const certificate = `${join(runtime, "cert.pem")} ${join(runtime, "key.pem")}`;
const originBridge = process.env.WEB_TEST_ORIGIN_BRIDGE === "1";
let config = readFileSync(join(root, "Caddyfile"), "utf8");
for (const origin of ["WEB_PARENT_ORIGIN", "WEB_STUDENT_ORIGIN"]) {
  config = config.replace(
    `{$${origin}} {`,
    `{$${origin}} {\n    bind 127.0.0.1\n    tls ${certificate}`,
  );
}
config = config.replaceAll(
  "reverse_proxy {$WEB_API_UPSTREAM} {",
  `reverse_proxy {$WEB_API_UPSTREAM} {\n            transport http {\n                tls_trust_pool file ${join(runtime, "ca.pem")}\n            }`,
);
if (originBridge)
  config = config.replaceAll("header_up Host {hostport}", "header_up Host localhost:18811");
const bridgeRoutes = originBridge
  ? `route {
      handle /browser/parent/* {
        reverse_proxy 127.0.0.1:8810 {
          header_up Host localhost:18443
          header_up X-Forwarded-For {http.request.header.X-Forwarded-For}
          flush_interval -1
        }
      }
      handle /browser/student/* {
        reverse_proxy 127.0.0.1:8810 {
          header_up Host 127.0.0.1:19443
          header_up X-Forwarded-For {http.request.header.X-Forwarded-For}
          flush_interval -1
        }
      }
      handle {
        respond 404
      }
    }`
  : "reverse_proxy 127.0.0.1:8810";
config = `{\n    admin off\n    auto_https disable_redirects\n    log {\n        level ERROR\n    }\n}\n${config}\nhttps://localhost:18811, https://127.0.0.1:18811 {\n    bind 127.0.0.1\n    tls ${certificate}\n    ${bridgeRoutes}\n}\n`;
const filename = join(runtime, "Caddyfile");
writeFileSync(filename, config);
const env = {
  ...process.env,
  WEB_PARENT_ORIGIN: "https://localhost:18443",
  WEB_STUDENT_ORIGIN: "https://127.0.0.1:19443",
  WEB_PARENT_ROOT: join(root, "dist/parent"),
  WEB_STUDENT_ROOT: join(root, "dist/student"),
  WEB_API_UPSTREAM: "https://localhost:18811",
  XDG_DATA_HOME: join(runtime, "data"),
  XDG_CONFIG_HOME: join(runtime, "config"),
};
execFileSync(
  caddy,
  ["validate", "--config", filename, "--adapter", "caddyfile"],
  { env, stdio: "inherit" },
);
function start(command, args, options) {
  const child = spawn(command, args, { ...options, stdio: "inherit" });
  children.push(child);
  child.on("error", (error) => {
    console.error(error);
    stop(1);
  });
  child.on("exit", (code) => {
    if (!stopping) stop(code || 1);
  });
}
start(caddy, ["run", "--config", filename, "--adapter", "caddyfile"], { env });
let ready = false;
for (let attempt = 0; attempt < 50; attempt++) {
  ready = await new Promise((resolve) => {
    const request = https.get(
      "https://127.0.0.1:19443",
      { ca: readFileSync(join(runtime, "ca.pem")) },
      (response) => {
        response.resume();
        resolve(response.statusCode === 200);
      },
    );
    request.on("error", () => resolve(false));
    request.setTimeout(1000, () => request.destroy());
  });
  if (ready) break;
  await new Promise((resolve) => setTimeout(resolve, 100));
}
if (!ready) throw new Error("Local HTTPS gateway did not start.");
start(python, ["-m", "tools.web_acceptance_server"], {
  cwd: server,
  env: {
    ...process.env,
    WEB_ACCEPTANCE_HTTPS: "1",
    WEB_ACCEPTANCE_TMP: runtime,
  },
});

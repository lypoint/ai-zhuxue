Demo payment does not require PEM files and never contacts WeChat.
For production, set WECHAT_KEY_DIR to a private directory outside this repository:
  merchant_private.pem  -- your merchant RSA private key (keep secret)
  platform_public.pem   -- WeChat Pay public key matching WECHAT_PLATFORM_SERIAL
Never put real keys in this directory or commit them.

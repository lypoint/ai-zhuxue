import { browserEvent } from "./api";

type Event = "student_page_view" | "guide_completed" | "teacher_selected" | "question_submitted" |
  "answer_received" | "answer_failed" | "answer_cancelled";
const pages = new Set(["chat", "stats", "history", "favorites", "learning", "grades", "assessments", "settings"]);
let enabled = false;
export function enableStudentAnalytics(value: boolean) { enabled = value; }
export function trackStudent(name: Event, path?: string) {
  if (__WEB_ROLE__ !== "student" || !enabled) return;
  const first = path?.split("/")[1];
  // No persistent browser identifier, content, teacher/student IDs or arbitrary parameters.
  browserEvent(name, path ? {page: pages.has(first || "") ? first! : "other"} : {});
}

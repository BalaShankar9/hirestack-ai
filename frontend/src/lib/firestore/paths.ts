import { collection, doc } from "firebase/firestore";
import { db } from "@/lib/firebase";

export const COLLECTIONS = {
  applications: "applications",
  users: "users",
  evidence: "evidence",
  tasks: "tasks",
  events: "events",
} as const;

export function applicationsCollectionRef() {
  return collection(db, COLLECTIONS.applications);
}

export function applicationDocRef(appId: string) {
  return doc(db, COLLECTIONS.applications, appId);
}

export function userEvidenceCollectionRef(userId: string) {
  return collection(db, COLLECTIONS.users, userId, COLLECTIONS.evidence);
}

export function userEvidenceDocRef(userId: string, evidenceId: string) {
  return doc(db, COLLECTIONS.users, userId, COLLECTIONS.evidence, evidenceId);
}

export function userTasksCollectionRef(userId: string) {
  return collection(db, COLLECTIONS.users, userId, COLLECTIONS.tasks);
}

export function userTaskDocRef(userId: string, taskId: string) {
  return doc(db, COLLECTIONS.users, userId, COLLECTIONS.tasks, taskId);
}

export function userEventsCollectionRef(userId: string) {
  return collection(db, COLLECTIONS.users, userId, COLLECTIONS.events);
}

export function userEventDocRef(userId: string, eventId: string) {
  return doc(db, COLLECTIONS.users, userId, COLLECTIONS.events, eventId);
}


import { workflowMode } from "@/shared/config/env"

import type { NotificationRepository, NotificationSettings, SystemNotice } from "../model/types"

import { apiNotificationRepository, getApiNotificationSettings, getApiSystemNotices, sendTestEmail } from "./api-repository"
import {
  getNotificationSettings as getDemoNotificationSettings,
  getSystemNotices as getDemoSystemNotices,
  notificationRepository as demoNotificationRepository,
} from "./local-repository"

export const notificationRepository: NotificationRepository =
  workflowMode === "api" ? apiNotificationRepository : demoNotificationRepository

export function getSystemNotices(): Promise<SystemNotice[]> {
  return workflowMode === "api" ? getApiSystemNotices() : getDemoSystemNotices()
}

export function getNotificationSettings(): Promise<NotificationSettings> {
  return workflowMode === "api" ? getApiNotificationSettings() : getDemoNotificationSettings()
}

export function sendTestNotification(recipient: string): Promise<void> {
  if (workflowMode !== "api") return Promise.reject(new Error("Test delivery requires the API workflow mode"))
  return sendTestEmail(recipient)
}

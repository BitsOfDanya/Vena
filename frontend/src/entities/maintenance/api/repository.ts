import { workflowMode } from "@/shared/config/env"

import type { ActionRepository } from "../model/types"

import { apiActionRepository } from "./api-repository"
import { actionRepository as demoActionRepository } from "./local-repository"

export const actionRepository: ActionRepository = workflowMode === "api" ? apiActionRepository : demoActionRepository

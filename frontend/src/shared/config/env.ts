export type DataMode = "demo" | "live"
export type WorkflowMode = "demo" | "api"

export const dataMode: DataMode = process.env.NEXT_PUBLIC_VENA_DATA_MODE === "live" ? "live" : "demo"

export const workflowMode: WorkflowMode = process.env.NEXT_PUBLIC_VENA_WORKFLOW_MODE === "api" ? "api" : "demo"

export const environmentLabel = process.env.NEXT_PUBLIC_VENA_ENVIRONMENT ?? (dataMode === "live" ? "live" : "demo")

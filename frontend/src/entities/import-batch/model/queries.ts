import { useQuery } from "@tanstack/react-query"

import { getImports } from "../api/imports"

export function useImports() {
  return useQuery({
    queryKey: ["imports", "list"], queryFn: getImports,
    refetchInterval: (query) => query.state.data?.some((item) => item.status === "pending" || item.status === "processing") ? 2_000 : false,
  })
}

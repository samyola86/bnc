import { AuditWorkspace } from "@/features/accounts/users";
export default async function AuditPage({ searchParams }: { searchParams: Promise<{ user?: string }> }) {
  return <AuditWorkspace initialUser={(await searchParams).user ?? ""} />;
}

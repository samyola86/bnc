import { Inbox } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
export function EmptyState({ title, description }: { title: string; description: string }) {
  return <Card><CardContent className="flex min-h-72 flex-col items-center justify-center p-8 text-center"><span className="mb-4 rounded-full bg-muted p-4"><Inbox className="size-6 text-muted-foreground" aria-hidden="true" /></span><h2 className="font-semibold">{title}</h2><p className="mt-2 max-w-md text-sm leading-6 text-muted-foreground">{description}</p></CardContent></Card>;
}

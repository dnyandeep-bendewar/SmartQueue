import { ArrowUpRight, Construction } from "lucide-react";
import { PageHeader } from "./PageHeader";
import { Badge } from "./ui/badge";
import { Card, CardContent } from "./ui/card";

interface PlaceholderPageProps {
  eyebrow: string;
  title: string;
  description: string;
  detail: string;
}

export function PlaceholderPage({
  eyebrow,
  title,
  description,
  detail,
}: PlaceholderPageProps) {
  return (
    <>
      <PageHeader eyebrow={eyebrow} title={title} description={description} />
      <Card>
        <CardContent className="flex flex-col items-start gap-5 py-9 sm:flex-row sm:items-center sm:py-11">
          <span className="flex size-12 shrink-0 items-center justify-center rounded-2xl bg-soft-accent text-accent">
            <Construction aria-hidden="true" size={22} />
          </span>
          <div className="min-w-0 flex-1">
            <Badge>
              <span className="size-1.5 rounded-full bg-accent" />
              Foundation ready
            </Badge>
            <h2 className="mt-3 text-lg font-semibold text-foreground">
              This workspace is being prepared
            </h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
              {detail}
            </p>
          </div>
          <ArrowUpRight
            aria-hidden="true"
            className="hidden text-muted-foreground sm:block"
            size={20}
          />
        </CardContent>
      </Card>
    </>
  );
}

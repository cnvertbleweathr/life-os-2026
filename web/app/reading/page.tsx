"use client";

import { useEffect, useState } from "react";
import { readingApi, type ReadingSummary } from "@/lib/api";
import {
  Card,
  PageHeader,
  SectionLabel,
  StatCard,
  Empty,
  Loading,
  ErrorState,
} from "@/components/ui/primitives";

export default function ReadingPage() {
  const [data, setData]   = useState<ReadingSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    readingApi
      .summary()
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <ErrorState message={error} />;
  if (!data) return <Loading />;

  return (
    <div>
      <PageHeader title="Reading" sub="via Hardcover" />
      <div className="p-6 space-y-6">
        <div className="grid grid-cols-3 gap-3">
          <StatCard label="Books read" value={data.books_read} accent />
          <StatCard label="Fiction" value={data.fiction_books} />
          <StatCard label="Nonfiction" value={data.nonfiction_books} />
        </div>

        <Card>
          <SectionLabel>Currently reading</SectionLabel>
          {/* Confirmed: this endpoint always returns [] today — there is no
              "currently reading" data source yet. Be honest about why,
              not just empty. */}
          <Empty
            message="Not tracked yet."
            detail="Hardcover only syncs finished books right now — in-progress tracking needs a pipeline addition."
          />
        </Card>
      </div>
    </div>
  );
}

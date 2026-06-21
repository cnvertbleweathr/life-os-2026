"use client";

import { useEffect, useState } from "react";
import { sportsApi } from "@/lib/api";
import { Card, PageHeader, SectionLabel, Empty, Loading } from "@/components/ui/primitives";

export default function SportsPage() {
  const [news, setNews] = useState<unknown[] | null>(null);

  useEffect(() => {
    sportsApi.news().then(setNews).catch(() => setNews([]));
  }, []);

  return (
    <div>
      <PageHeader title="Sports" sub="News + team tracking" />
      <div className="p-6">
        <Card>
          <SectionLabel>Sports news</SectionLabel>
          {news === null ? (
            <Loading />
          ) : news.length === 0 ? (
            <Empty
              message="Not configured."
              detail="NEWS_API_KEY isn't set in .env — expected, not a bug."
            />
          ) : (
            <pre className="text-2xs text-muted">{JSON.stringify(news, null, 2)}</pre>
          )}
        </Card>
      </div>
    </div>
  );
}

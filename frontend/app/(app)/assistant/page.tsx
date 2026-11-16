"use client";

import { Bot, Database, Info, Lightbulb, Loader2, SendHorizontal, Trash2, User, WifiOff } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { InsightList } from "@/components/shared/insight-list";
import { PageHeader } from "@/components/shared/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { api, useApi, useApiMutation } from "@/hooks/use-api";
import { useAuth } from "@/lib/auth";
import { humanize } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { AIStatus, AssistantReply, ChatMessage, Insight } from "@/types/api";

interface Turn extends ChatMessage {
  id: number;
  reply?: AssistantReply;
  failed?: boolean;
}

const EXAMPLES = [
  "What were today's sales?",
  "Which products sold the most this week?",
  "Which ingredients are running low?",
  "What should we reorder?",
  "What is the forecast for tomorrow?",
  "Compare this week's sales with last week",
];

// Only the last turns are sent as context; the server caps history at 20 messages.
const HISTORY_LIMIT = 10;
let turnCounter = 0;

export default function AssistantPage() {
  const { t } = useI18n();
  const { can } = useAuth();
  const status = useApi<AIStatus>(["ai", "status"], "/ai/status");
  const insights = useApi<{ insights: Insight[] }>(["ai", "insights"], can("analytics:read") ? "/ai/insights" : null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  const chat = useApiMutation(
    (message: string) =>
      api<AssistantReply>("/ai/chat", {
        method: "POST",
        body: {
          message,
          history: turns
            .filter((x) => !x.failed)
            .slice(-HISTORY_LIMIT)
            .map(({ role, content }) => ({ role, content })),
        },
      }),
    {
      silent: true,
      onSuccess: (reply) => setTurns((ts) => [...ts, { id: ++turnCounter, role: "assistant", content: reply.answer, reply }]),
    },
  );

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns, chat.isPending]);

  function send(text: string) {
    const message = text.trim();
    if (!message || chat.isPending) return;
    setTurns((ts) => [...ts, { id: ++turnCounter, role: "user", content: message }]);
    setDraft("");
    chat.mutate(message, {
      onError: (error) =>
        setTurns((ts) => [
          ...ts,
          { id: ++turnCounter, role: "assistant", content: error instanceof Error ? error.message : "The assistant is unavailable.", failed: true },
        ]),
    });
  }

  const offline = status.data && !status.data.llm_configured;

  return (
    <>
      <PageHeader
        title={t("AI Assistant")}
        description="Ask about sales, menu items, stock, forecasts and reorder suggestions. Answers come only from your restaurant's data through read-only tools."
        actions={
          turns.length ? (
            <Button variant="outline" size="sm" onClick={() => setTurns([])}>
              <Trash2 /> Clear chat
            </Button>
          ) : null
        }
      />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
        <Card className="min-h-[60dvh] gap-0 py-0">
          {offline ? (
            <div className="flex gap-2 border-b bg-muted/50 px-5 py-3 text-sm">
              <WifiOff className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
              <p>
                <span className="font-medium">Offline mode.</span> {status.data?.message}
              </p>
            </div>
          ) : null}
          <div className="flex-1 overflow-y-auto px-5 py-4" aria-live="polite">
            {turns.length ? (
              <ol className="grid gap-4">
                {turns.map((turn) => (
                  <MessageBubble key={turn.id} turn={turn} hideNotice={!!offline} />
                ))}
                {chat.isPending ? (
                  <li className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="size-4 animate-spin" aria-hidden /> Looking at your data…
                  </li>
                ) : null}
              </ol>
            ) : (
              <div className="grid place-items-center gap-4 py-10 text-center">
                <Bot className="size-10 text-muted-foreground" aria-hidden />
                <div>
                  <p className="font-medium">Ask a question about your restaurant</p>
                  <p className="text-sm text-muted-foreground">For example:</p>
                </div>
                <div className="flex max-w-2xl flex-wrap justify-center gap-2">
                  {EXAMPLES.map((q) => (
                    <Button key={q} variant="outline" size="sm" onClick={() => send(q)}>
                      {q}
                    </Button>
                  ))}
                </div>
              </div>
            )}
            <div ref={endRef} />
          </div>
          <form
            className="flex items-end gap-2 border-t p-3"
            onSubmit={(e) => {
              e.preventDefault();
              send(draft);
            }}
          >
            <Textarea
              aria-label="Message"
              rows={2}
              maxLength={1000}
              placeholder="Ask about sales, stock or forecasts…"
              className="min-h-0 resize-none"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  send(draft);
                }
              }}
            />
            <Button type="submit" size="icon" aria-label="Send" disabled={!draft.trim() || chat.isPending}>
              <SendHorizontal />
            </Button>
          </form>
        </Card>
        <div className="grid content-start gap-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Info className="size-4" aria-hidden /> How it works
              </CardTitle>
            </CardHeader>
            <CardContent className="grid gap-2 text-sm text-muted-foreground">
              <p>
                {status.data?.llm_configured
                  ? `Natural-language answers by ${status.data.model}.`
                  : "Rule-based answers for common questions; no external AI service is called."}
              </p>
              <p>
                The assistant can only call these read-only tools, limited by your role. It cannot change data, place orders or
                see other restaurants.
              </p>
              <ul className="flex flex-wrap gap-1.5">
                {(status.data?.available_tools ?? []).map((name) => (
                  <li key={name}>
                    <Badge variant="outline">{humanize(name.replace(/^get_/, ""))}</Badge>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
          {insights.data?.insights.length ? (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Lightbulb className="size-4 text-primary" aria-hidden /> Insights
                </CardTitle>
                <CardDescription>Calculated by rules from your data</CardDescription>
              </CardHeader>
              <CardContent>
                <InsightList insights={insights.data.insights} className="-mx-2" />
              </CardContent>
            </Card>
          ) : null}
        </div>
      </div>
    </>
  );
}

function MessageBubble({ turn, hideNotice }: { turn: Turn; hideNotice: boolean }) {
  const mine = turn.role === "user";
  return (
    <li className={cn("flex gap-3", mine && "flex-row-reverse")}>
      <span
        aria-hidden
        className={cn(
          "grid size-8 shrink-0 place-items-center rounded-full",
          mine ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground",
        )}
      >
        {mine ? <User className="size-4" /> : <Bot className="size-4" />}
      </span>
      <div className={cn("grid max-w-[85%] gap-1.5", mine && "justify-items-end")}>
        <span className="sr-only">{mine ? "You said:" : "Assistant:"}</span>
        <div
          className={cn(
            "rounded-lg px-3.5 py-2.5 text-sm whitespace-pre-line",
            mine ? "bg-primary text-primary-foreground" : turn.failed ? "border border-status-critical/40 bg-status-critical/5" : "bg-muted",
          )}
        >
          {turn.content}
        </div>
        {turn.reply ? (
          <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
            <Badge variant="outline">{turn.reply.mode === "llm" ? (turn.reply.model ?? "AI model") : "Rule-based"}</Badge>
            {turn.reply.tools_used.map((tool, index) => (
              <span key={`${tool.name}-${index}`} className="inline-flex items-center gap-1" title={JSON.stringify(tool.arguments)}>
                <Database className="size-3" aria-hidden />
                {humanize(tool.name.replace(/^get_/, ""))}
              </span>
            ))}
            {turn.reply.notice && !hideNotice ? <span>· {turn.reply.notice}</span> : null}
          </div>
        ) : null}
      </div>
    </li>
  );
}

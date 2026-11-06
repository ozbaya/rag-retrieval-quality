import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  if (process.env.ASK_ENABLED !== "1") return NextResponse.json({ detail: "Not enabled" }, { status: 404 });
  const body = await req.json().catch(() => null);
  const question = typeof body?.question === "string" ? body.question.slice(0, 300) : "";
  if (question.trim().length < 3) return NextResponse.json({ detail: "Question too short" }, { status: 400 });
  const ip = (req.headers.get("x-forwarded-for") ?? "unknown").split(",")[0].trim();
  const res = await fetch(`${process.env.BACKEND_URL}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${process.env.BACKEND_TOKEN}`, "X-Client-IP": ip },
    body: JSON.stringify({ question }),
    signal: AbortSignal.timeout(35_000),
  }).catch(() => null);
  if (!res) return NextResponse.json({ detail: "Backend unavailable" }, { status: 502 });
  return NextResponse.json(await res.json().catch(() => ({ detail: "Bad response" })), { status: res.status });
}


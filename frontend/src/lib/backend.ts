import "server-only";

const BASE = process.env.BACKEND_URL!;
const TOKEN = process.env.BACKEND_TOKEN!;

export async function backendGet<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { Authorization: `Bearer ${TOKEN}` },
    next: { revalidate: 300 },
  });
  if (!res.ok) throw new Error(`backend ${path} -> ${res.status}`);
  return res.json() as Promise<T>;
}


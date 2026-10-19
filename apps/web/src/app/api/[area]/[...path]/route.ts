import { proxyApiRequest } from "../../../../lib/api-proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Context = { params: Promise<{ area: string; path: string[] }> };
async function handle(request: Request, context: Context) {
  const { area, path } = await context.params;
  return proxyApiRequest(request, area, path);
}

export { handle as GET, handle as POST, handle as DELETE };

import { Router, Request, Response, NextFunction } from 'express';
import { config } from '../config';
import { feishuDocumentService } from '../integrations/feishu/document';
import { feishuBitableService } from '../integrations/feishu/bitable';

const router = Router();

/**
 * 校验 X-Internal-Secret header。
 * Python Agent 调用内部接口时须携带此 header。
 */
function verifyInternalSecret(req: Request, res: Response, next: NextFunction): void {
  const secret = config.pythonAgent.internalSecret;

  // internalSecret 未配置时（空字符串），仅在开发环境放行；生产环境必须配置
  if (!secret) {
    if (config.nodeEnv === 'production') {
      res.status(500).json({ ok: false, error: 'INTERNAL_SECRET is not configured in production' });
      return;
    }
    next();
    return;
  }

  const provided = req.headers['x-internal-secret'];
  if (provided !== secret) {
    res.status(401).json({ ok: false, error: 'Invalid X-Internal-Secret' });
    return;
  }

  next();
}

/**
 * POST /internal/feishu/docs/read
 * 读取飞书云文档，将文档内容以 Markdown 格式返回。
 *
 * Request body: { doc_token: string }
 * Response: { ok: true, content: string } | { ok: false, error_code, error_message }
 */
router.post('/internal/feishu/docs/read', verifyInternalSecret, async (req: Request, res: Response) => {
  const { doc_token } = req.body as { doc_token?: string };

  if (!doc_token) {
    res.status(400).json({ ok: false, error_code: 'MISSING_PARAM', error_message: 'doc_token is required' });
    return;
  }

  try {
    const content = await feishuDocumentService.readDocAsMarkdown(doc_token);
    res.json({ ok: true, content });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    res.status(502).json({ ok: false, error_code: 'FEISHU_API_ERROR', error_message: message });
  }
});

/**
 * POST /internal/feishu/bitable/query
 * 查询飞书多维表格。Python Agent 通过此接口读取记忆/求职记录等 Bitable 数据。
 *
 * Request body: {
 *   app_token: string,         // Bitable App Token
 *   table_id: string,          // 数据表 ID
 *   filter?: object,           // 飞书 filter 条件（conjunction + conditions 格式）
 *   sort?: object[],           // 排序
 *   page_size?: number,        // 每页条数（最大 500）
 *   page_token?: string,       // 翻页 token
 * }
 * Response: { ok: true, data: { items, total, has_more, page_token? } }
 */
router.post('/internal/feishu/bitable/query', verifyInternalSecret, async (req: Request, res: Response) => {
  const { app_token, table_id, filter, sort, page_size, page_token } = req.body as {
    app_token?: string;
    table_id?: string;
    filter?: Record<string, unknown>;
    sort?: Record<string, unknown>[];
    page_size?: number;
    page_token?: string;
  };

  if (!app_token || !table_id) {
    res.status(400).json({ ok: false, error_code: 'MISSING_PARAM', error_message: 'app_token and table_id are required' });
    return;
  }

  const searchBody: Record<string, unknown> = {
    page_size: Math.min(page_size ?? 20, 500),
  };
  if (filter) searchBody['filter'] = filter;
  if (sort) searchBody['sort'] = sort;
  if (page_token) searchBody['page_token'] = page_token;

  try {
    const result = await feishuBitableService.searchRecordsInTable(
      { appToken: app_token, tableId: table_id },
      searchBody,
    );
    res.json({
      ok: true,
      data: {
        items: result.items,
        has_more: result.has_more,
        page_token: result.page_token ?? null,
      },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    res.status(502).json({ ok: false, error_code: 'FEISHU_API_ERROR', error_message: message });
  }
});

/**
 * POST /internal/feishu/files/upload
 * 上传文件到飞书（stub）
 */
router.post('/internal/feishu/files/upload', verifyInternalSecret, (_req: Request, res: Response) => {
  res.json({ ok: true, data: null, note: 'stub' });
});

export default router;

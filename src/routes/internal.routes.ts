import { Router, Request, Response, NextFunction } from 'express';
import { config } from '../config';
import { feishuDocumentService } from '../integrations/feishu/document';

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
 * 查询飞书多维表格（stub）
 */
router.post('/internal/feishu/bitable/query', verifyInternalSecret, (_req: Request, res: Response) => {
  res.json({ ok: true, data: null, note: 'stub' });
});

/**
 * POST /internal/feishu/files/upload
 * 上传文件到飞书（stub）
 */
router.post('/internal/feishu/files/upload', verifyInternalSecret, (_req: Request, res: Response) => {
  res.json({ ok: true, data: null, note: 'stub' });
});

export default router;

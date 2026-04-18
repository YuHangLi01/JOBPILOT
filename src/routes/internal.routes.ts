import { Router, Request, Response, NextFunction } from 'express';
import { config } from '../config';

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
 * 读取飞书云文档（stub，正式实现见下周迭代）
 */
router.post('/internal/feishu/docs/read', verifyInternalSecret, (_req: Request, res: Response) => {
  res.json({ ok: true, data: null, note: 'stub' });
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

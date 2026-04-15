import { Router, Request, Response } from 'express';
import { feishuEventController } from '../controllers/feishu-event.controller';

const router = Router();

/**
 * 健康检查
 * GET /health
 */
router.get('/health', (_req: Request, res: Response) => {
  res.json({
    status: 'ok',
    service: 'JobPilot for Feishu',
    version: '1.0.0',
    timestamp: new Date().toISOString(),
  });
});

/**
 * 飞书事件订阅 Webhook
 * POST /webhook/feishu
 *
 * 飞书开放平台 → 事件订阅 → 请求地址 配置为：
 * https://your-domain.com/webhook/feishu
 */
router.post('/webhook/feishu', (req: Request, res: Response) => {
  feishuEventController.handleEvent(req, res);
});

/**
 * 手动测试入口（开发调试用）
 * POST /api/test/analyze
 * Body: { "jd_text": "..." }
 *
 * 直接调用编排器，不经过飞书事件体系，方便本地调试
 */
router.post('/api/test/analyze', async (req: Request, res: Response) => {
  try {
    const { jd_text } = req.body as { jd_text?: string };

    if (!jd_text) {
      res.status(400).json({ error: '请在 body 中传入 jd_text 字段' });
      return;
    }

    // 动态导入避免循环依赖
    const { orchestratorService } = await import('../services/orchestrator.service');
    const result = await orchestratorService.execute(jd_text);

    res.json({
      success: true,
      data: result,
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    res.status(500).json({ success: false, error: msg });
  }
});

export default router;

import { Router, Request, Response } from 'express';
import multer from 'multer';
import { feishuEventController } from '../controllers/feishu-event.controller';
import { RESUME_MAX_FILE_SIZE_BYTES } from '../constants';
import { resumeIngestionService } from '../services/resume-ingestion.service';
import { validateResumePdf } from '../utils/validator';

const router = Router();
const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: RESUME_MAX_FILE_SIZE_BYTES, files: 1 },
});

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

router.post('/api/test/resume', (req: Request, res: Response) => {
  upload.single('resume')(req, res, async (err: unknown) => {
    if (err) {
      const msg = err instanceof Error ? err.message : String(err);
      res.status(400).json({ success: false, error: `上传失败：${msg}` });
      return;
    }

    try {
      const userId = String(req.body?.user_id || req.body?.userId || '').trim();
      if (!userId) {
        res.status(400).json({ success: false, error: '请通过 user_id 字段传入用户 ID。' });
        return;
      }

      const file = req.file;
      const validation = validateResumePdf({
        filename: file?.originalname,
        mimetype: file?.mimetype,
        size: file?.size,
        buffer: file?.buffer,
      });
      if (!validation.valid || !file?.buffer) {
        res.status(400).json({ success: false, error: validation.error || '未收到 PDF 简历。' });
        return;
      }

      const result = await resumeIngestionService.ingest({
        userId,
        filename: file.originalname,
        buffer: file.buffer,
        source: 'http_upload',
      });

      res.json({
        success: true,
        data: {
          filename: result.filename,
          source: result.source,
          recordId: result.writeResult.recordId,
          profilePatch: result.profilePatch,
          textPreview: result.extractedText.slice(0, 300),
        },
      });
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      res.status(500).json({ success: false, error: msg });
    }
  });
});

export default router;

import express from 'express';
import routes from './routes';
import { createLogger } from './utils/logger';

const log = createLogger('App');

const app = express();

// ===== 中间件 =====

// 解析 JSON body
app.use(express.json({ limit: '1mb' }));
app.use(express.urlencoded({ extended: true }));

// 请求日志中间件
app.use((req, _res, next) => {
  log.info(`${req.method} ${req.path}`, {
    ip: req.ip,
    userAgent: req.get('User-Agent')?.substring(0, 80),
  });
  next();
});

// ===== 路由 =====
app.use(routes);

// ===== 404 =====
app.use((_req, res) => {
  res.status(404).json({ error: 'Not Found' });
});

// ===== 全局错误处理 =====
app.use((err: Error, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
  log.error('未捕获的请求错误', err.message);
  res.status(500).json({ error: '服务内部错误，请稍后重试' });
});

export default app;

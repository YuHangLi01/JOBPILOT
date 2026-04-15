import { config } from './config';
import app from './app';
import { createLogger } from './utils/logger';

const log = createLogger('Server');

const PORT = config.port;

app.listen(PORT, () => {
  log.info(`🚀 JobPilot for Feishu 服务已启动`);
  log.info(`   端口: ${PORT}`);
  log.info(`   环境: ${config.nodeEnv}`);
  log.info(`   健康检查: http://localhost:${PORT}/health`);
  log.info(`   飞书 Webhook: http://localhost:${PORT}/webhook/feishu`);
  log.info(`   测试接口: http://localhost:${PORT}/api/test/analyze`);
  log.info(`   LLM 模型: ${config.llm.model}`);
  log.info(`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`);
});

// 优雅退出
process.on('SIGTERM', () => {
  log.info('收到 SIGTERM 信号，正在优雅退出...');
  process.exit(0);
});

process.on('SIGINT', () => {
  log.info('收到 SIGINT 信号，正在优雅退出...');
  process.exit(0);
});

process.on('unhandledRejection', (reason) => {
  log.error('未处理的 Promise 拒绝', reason instanceof Error ? reason.message : String(reason));
});

process.on('uncaughtException', (err) => {
  log.error('未捕获的异常', err.message);
  process.exit(1);
});

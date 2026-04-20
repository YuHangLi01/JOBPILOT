import { describe, it, expect } from 'vitest';
import { detectIntent } from '../intent-detector.service';

const JD_TEXT = `岗位职责：负责前端架构设计和核心模块开发，与产品设计团队协作，推动技术方案落地。
任职要求：5年以上前端开发经验，熟悉 React/Vue，具有良好的工程化能力。
我们提供有竞争力的薪资和宽松的远程工作环境。欢迎加入我们的团队！`;

describe('detectIntent', () => {
  it('returns jd_routing for JD-like text', () => {
    expect(detectIntent(JD_TEXT, false)).toBe('jd_routing');
  });

  it('returns interview_reply when user is in interview', () => {
    expect(detectIntent('我有三年 React 开发经验', true)).toBe('interview_reply');
  });

  it('returns interview_reply even for JD-like text when in interview', () => {
    expect(detectIntent(JD_TEXT, true)).toBe('interview_reply');
  });

  it('returns general_chat for short text', () => {
    expect(detectIntent('你好', false)).toBe('general_chat');
  });

  it('returns general_chat for long text without JD keywords', () => {
    const text = '我想了解一下行业薪资水平，最近市场上的行情怎么样？大家都是怎么谈薪资的？能给点建议吗？';
    expect(detectIntent(text, false)).toBe('general_chat');
  });

  it('returns jd_routing when岗位要求 keyword present and text long enough', () => {
    const text =
      '岗位要求：本科及以上学历，计算机相关专业，3年以上 Java 开发经验，熟悉 Spring Boot，了解微服务架构，' +
      '具备良好的沟通能力和团队协作精神，有大厂经验者优先。';
    expect(detectIntent(text, false)).toBe('jd_routing');
  });
});

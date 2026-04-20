/**
 * 飞书交互卡片构建器。
 */

export interface FeishuInteractiveCard {
  config?: { wide_screen_mode?: boolean };
  header?: {
    title: { tag: string; content: string };
    template?: string;
  };
  elements: unknown[];
}

/**
 * 构建模拟面试邀请卡片。
 *
 * 卡片包含公司/岗位信息和一个"开始面试"按钮。
 * 点击按钮后飞书触发 card.action.trigger 事件，value 中携带 action/company/position。
 */
export function buildInterviewInvitationCard(
  company: string,
  position: string,
  ctaText: string,
): FeishuInteractiveCard {
  return {
    config: { wide_screen_mode: true },
    header: {
      title: { tag: 'plain_text', content: '模拟面试邀请' },
      template: 'blue',
    },
    elements: [
      {
        tag: 'div',
        text: {
          tag: 'lark_md',
          content: `**公司**：${company}\n**岗位**：${position}\n\n已完成 JD 分析，是否开始模拟面试？`,
        },
      },
      {
        tag: 'action',
        actions: [
          {
            tag: 'button',
            text: { tag: 'plain_text', content: ctaText },
            type: 'primary',
            value: { action: 'start_interview', company, position },
          },
        ],
      },
    ],
  };
}

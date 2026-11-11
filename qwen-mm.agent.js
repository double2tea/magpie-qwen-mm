export const agent = {
  id: "qwen-mm",
  name: "Qwen MM",
  icon: "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCA2NCA2NCI+PHJlY3Qgd2lkdGg9IjY0IiBoZWlnaHQ9IjY0IiByeD0iMTUiIGZpbGw9IiM2MTU1ZjUiLz48cGF0aCBkPSJNMjAgMThoMjR2MjJIMjB6IiBmaWxsPSJub25lIiBzdHJva2U9IndoaXRlIiBzdHJva2Utd2lkdGg9IjQiLz48cGF0aCBkPSJtNDQgMjYgMTAtNnYyMGwtMTAtNk0yNyA0OGgxMCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSJ3aGl0ZSIgc3Ryb2tlLXdpZHRoPSI0IiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiLz48L3N2Zz4=",
  dir: "~/.qwen-mm-plugins",
  config: "~/.config/magpie/qwen-mm/config",
  format: "env",
  ua: ["qwen-mm-plugins"],
  notice: "在 Qwen MM 页面分别选择 VL 与 Omni 模型。",
};

export function connect({ gateway }) {
  return {
    DASHSCOPE_BASE_URL: gateway.v1,
    DASHSCOPE_API_KEY: gateway.key,
  };
}

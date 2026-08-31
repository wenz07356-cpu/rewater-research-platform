# Query V4 局部优化建议：Web 来源链接可点击展示

## 1. 文档目的

本文分析最终答案中的 Web 来源为什么只能显示为普通文本，并提供可点击链接的局部优化方案和实施步骤。

本文只描述方案，不修改代码。

涉及范围：

- `app/rag/query/answer_output_service.py`
- `app/resources/prompts/answer_out.prompt`
- `app/process/query/page/chat.html`
- `app/api/schemas/query.py`
- `app/api/http/query_server.py`
- `tests/test_query_services.py`

## 2. 问题确认

示例答案：

```text
应用场景不断拓展……每年节约自来水约12万吨，节省水费50万元以上
[网络搜索/http://www.szlhq.gov.cn/lhswj/gkmlpt/content/12/12884/post_12884500.html]。
```

当前 URL 无法点击的问题属实，但原因不是后端没有返回链接，而是前端把完整答案当纯文本渲染。

### 2.1 后端已经提供 URL

`build_source_label()` 对 Web 候选生成：

```python
return f"[网络搜索/{url}]"
```

`answer_out.prompt` 也要求模型原样使用：

```text
[网络搜索/url]
```

非流式 HTTP 响应和流式 SSE 最终事件都会把完整答案作为字符串返回。当前 API 没有丢失 URL。

### 2.2 前端明确按纯文本渲染

聊天页的 `renderAnswerWithImages()` 当前执行：

```javascript
textEl.textContent = text;
```

`textContent` 的安全特性是不会解析 HTML，也不会解析 Markdown。因此以下内容都会被显示成普通文字：

```text
[网络搜索/http://example.com]
[网络搜索](http://example.com)
<a href="http://example.com">网络搜索</a>
```

所以只修改后端 Prompt，把来源格式改成 Markdown 链接，并不能解决当前页面的问题。必须同时让前端识别来源标签并创建链接元素。

### 2.3 当前图片链接为什么可以点击

聊天页对图片 URL 已采用 DOM API：

```javascript
const link = document.createElement('a');
link.href = safeUrl;
link.target = '_blank';
link.rel = 'noopener noreferrer';
```

这说明当前页面已经有安全创建链接的实现模式。Web 来源链接可以沿用同样的方式，而不需要引入完整 Markdown 渲染器。

## 3. 方案对比

### 3.1 方案 A：前端解析现有来源标签，推荐

保持后端输出不变：

```text
[网络搜索/http://example.com/page]
```

前端识别该结构并渲染为：

```html
<a href="http://example.com/page" target="_blank"
   rel="noopener noreferrer">网络搜索</a>
```

用户看到的效果可以是：

```text
[网络搜索]
```

其中“网络搜索”四个字可以点击，鼠标悬停时浏览器显示真实 URL。

优点：

- 修改范围最小。
- 不改变后端来源标签、Prompt、历史记录和 API Schema。
- 不需要引入 Markdown 第三方库。
- 可以使用 DOM API 安全创建链接，避免 XSS。
- 流式与非流式答案可以复用同一个渲染入口。

缺点：

- 前端需要维护一个来源标签解析函数。
- 如果未来增加更多富文本语法，需要继续扩展渲染规则。

这是当前项目最适合的局部优化方案。

### 3.2 方案 B：后端输出 Markdown，暂不推荐作为本次局部优化

把来源改为：

```markdown
[网络搜索](http://example.com/page)
```

同时前端引入 Markdown 渲染器和 HTML Sanitizer。

优点：

- 格式通用。
- 后续可以支持标题、列表、表格和代码块等富文本。

缺点：

- 当前页面使用 `textContent`，只改后端不会生效。
- 需要引入、配置和维护 Markdown 渲染与 HTML 清洗能力。
- 流式输出中 Markdown 标签可能暂时不完整，需要处理增量渲染。
- 会改变当前 Prompt、测试、历史答案和来源格式契约。
- 如果清洗配置错误，会引入 XSS 风险。

如果以后准备整体升级答案富文本能力，可以单独设计 Markdown 渲染；本次不必扩大范围。

### 3.3 方案 C：API 返回结构化 citations，长期方案

API 在 `answer` 之外返回：

```json
{
  "answer": "……",
  "citations": [
    {
      "type": "web",
      "label": "网络搜索",
      "url": "http://example.com/page",
      "title": "网页标题"
    }
  ]
}
```

优点：

- 展示与模型文本解耦。
- 方便去重、来源列表、卡片展示和点击统计。
- 不需要信任模型生成的 URL 格式。

缺点：

- 需要修改 Query state、API Schema、SSE、历史记录和前端。
- 需要解决正文中的事实与 citation 之间如何稳定对应。
- 超出当前局部优化范围。

该方案适合作为后续正式引用系统的方向，不建议本次直接实施。

## 4. 推荐目标设计

### 4.1 后端来源契约保持不变

继续使用：

```text
[网络搜索/url]
```

原因：

- 当前 Prompt、答案后处理和测试已经使用该格式。
- URL 已来自精排后的 Web 候选，不需要额外生成。
- 保持后端兼容可以让本次变更集中在展示层。

本地来源继续显示为普通文字：

```text
[本地知识库/file_title/section_title]
```

本地来源当前没有可访问 URL，不应渲染成虚假的链接。

### 4.2 前端新增安全的来源标签渲染

建议增加一个职责单一的函数，例如：

```text
renderAnswerTextWithSourceLinks(container, text)
```

核心职责：

1. 查找完整的 `[网络搜索/http://...]` 或 `[网络搜索/https://...]` 标签。
2. 标签前后的普通文本使用 `document.createTextNode()`。
3. URL 通过安全校验后使用 `document.createElement('a')` 创建链接。
4. 不合法或不完整的标签原样作为文本显示。
5. 不解析任意 HTML。

可以使用受限匹配规则：

```javascript
/\[网络搜索\/(https?:\/\/[^\]\s]+)\]/g
```

该规则只识别完整标签和 HTTP/HTTPS URL，不应放宽到任意协议。

注意：正则只是识别候选，匹配后仍需使用 URL API 做第二次协议校验。

### 4.3 链接显示形式

建议不要把很长的 URL 全部显示给用户。推荐显示：

```text
[网络搜索]
```

其中“网络搜索”为链接，真实地址放在 `href` 中。

也可以使用：

```text
[网络搜索：打开原文]
```

建议通过 `title` 属性提供完整 URL：

```javascript
link.title = safeUrl;
```

### 4.4 链接属性

每个外部链接建议设置：

```javascript
link.target = '_blank';
link.rel = 'noopener noreferrer';
link.referrerPolicy = 'no-referrer';
```

含义：

- `target="_blank"`：新标签页打开，不中断当前对话。
- `noopener`：新页面不能通过 `window.opener` 控制原页面。
- `noreferrer`：减少来源页获得当前页面信息。
- `referrerPolicy="no-referrer"`：进一步明确不发送 Referer。

## 5. 安全边界

链接渲染不能直接使用模型答案拼接 `innerHTML`。

### 5.1 只允许 HTTP 和 HTTPS

应拒绝：

```text
javascript:
data:
file:
vbscript:
```

建议校验流程：

1. 从完整来源标签中提取 URL。
2. 使用 `new URL(rawUrl)` 解析。
3. 检查 `parsed.protocol` 只能是 `http:` 或 `https:`。
4. 校验通过才创建 `<a>`。
5. 失败时原样显示文本，不创建链接。

### 5.2 不使用原始 innerHTML

禁止：

```javascript
container.innerHTML = answerText;
```

也不应简单执行：

```javascript
container.innerHTML = answerText.replace(..., '<a ...>');
```

模型答案、网页摘要和 URL 都属于外部输入。应使用：

- `document.createTextNode()` 创建普通文本；
- `document.createElement('a')` 创建链接；
- DOM 属性赋值设置 `href`、`target` 和 `rel`。

### 5.3 URL 显示与 URL 跳转使用同一校验结果

不要一边显示清洗后的 URL，一边让 `href` 使用原始 URL。页面展示、`title` 和 `href` 应统一使用通过校验后的地址。

## 6. 流式与非流式兼容

当前聊天页的非流式结果、流式 delta 和流式 final 最终都会进入 `renderAnswerWithImages()`，因此应在这个统一入口内调用来源链接渲染函数。

### 6.1 非流式

完整答案一次返回，可以直接解析全部来源标签并创建链接。

### 6.2 流式

流式过程中可能出现不完整文本：

```text
[网络搜索/http://example.co
```

此时不应提前创建链接，应按普通文本显示。等后续 delta 补齐右方括号后，再在下一次整体重绘时识别成完整链接。

当前页面每次收到 delta 都会累计 `rawAnswerText` 并重新调用 `renderAnswerWithImages()`，所以只要解析函数坚持“只转换完整标签”，就能自然兼容流式输出。

最终 `final` 或 `final_answer` 事件到达后，必须再次使用完整答案渲染，确保链接最终可点击。

### 6.3 历史记录

历史助手消息也应进入同一个安全渲染函数，避免出现：

- 新回答链接可点击；
- 刷新后历史回答又退化为普通文本。

如果当前历史消息已经统一调用 `renderAnswerWithImages()`，则无需单独维护第二套逻辑，只需确认回归结果。

## 7. 建议实施步骤

以下是后续实施步骤，本次不执行代码修改。

### 步骤一：固定来源格式

1. 保持 `build_source_label()` 的 `[网络搜索/url]` 输出不变。
2. 保持 `answer_out.prompt` 的来源要求不变。
3. 保持 `QueryResponse.answer` 仍为字符串，不调整 API Schema。
4. 明确只有 `http://` 和 `https://` Web 标签可转为链接。

### 步骤二：实现 URL 安全校验函数

建议增加类似：

```text
normalizeExternalSourceUrl(rawUrl) -> string | null
```

步骤：

1. 去除首尾空白。
2. 使用 URL API 解析。
3. 检查协议白名单。
4. 返回规范 URL；异常或协议不允许时返回 `null`。

如果复用当前图片 URL 的 `normalizeUrl()`，需要先确认它是否严格限制协议；不能只依赖字符串以 `http` 开头。

### 步骤三：实现来源标签 DOM 渲染函数

1. 遍历答案中的完整 Web 来源标签。
2. 把匹配前的内容作为文本节点追加。
3. 校验提取到的 URL。
4. 合法时创建 `<a>`；非法时追加原始标签文本。
5. 继续处理剩余文本。
6. 全程不使用模型答案构造 `innerHTML`。

### 步骤四：接入统一答案渲染

将当前：

```javascript
textEl.textContent = text;
```

替换为调用来源标签 DOM 渲染函数。

保持图片提取、图片展示和图片链接逻辑不变。来源链接应放在 `answer-text` 内，图片仍放在 `answer-images` 中。

### 步骤五：增加链接样式

建议为来源链接增加专用 class，例如：

```text
answer-source-link
```

样式应满足：

- 与普通正文有明显区别；
- 支持 hover 和键盘 focus；
- 不显示过长 URL；
- 颜色在当前背景下满足可读性；
- 保留浏览器可识别的链接语义。

### 步骤六：补充测试

至少覆盖：

1. 一个 HTTP Web 来源可点击。
2. 一个 HTTPS Web 来源可点击。
3. 同一答案中多个 Web 来源都可点击。
4. URL 带 query string 时跳转地址完整。
5. Web 来源后紧跟中文句号时，句号不进入 URL。
6. `[本地知识库/...]` 保持普通文本。
7. 不完整的 `[网络搜索/...` 保持普通文本。
8. `javascript:`、`data:` 和 `file:` 不生成链接。
9. 普通答案中的任意 URL 不自动转为链接，只有正式来源标签才转换。
10. 流式标签被多个 delta 拆开时，补齐后可以点击。
11. 非流式、流式 final 和历史消息展示一致。
12. 图片展示与来源链接同时存在时互不影响。

### 步骤七：浏览器手动验证

1. 使用真实 WebSearch 查询获得至少一个网页来源。
2. 检查链接在新标签页打开。
3. 检查当前对话状态没有丢失。
4. 检查链接元素包含 `noopener noreferrer`。
5. 检查长 URL 不破坏消息气泡布局。
6. 检查键盘 Tab 可以聚焦链接，Enter 可以打开。
7. 检查移动端或窄窗口下链接标签不会溢出。

## 8. 验收标准

满足以下条件即可认为优化完成：

1. Web 来源显示为清晰的可点击链接。
2. 点击后在新标签页打开原始网页。
3. 非流式、流式完成态和历史消息行为一致。
4. 本地来源显示不受影响。
5. 图片渲染不受影响。
6. 非 HTTP/HTTPS 协议不会生成链接。
7. 页面没有使用未清洗的答案字符串写入 `innerHTML`。
8. 后端答案、Prompt、SSE 和 API Schema 保持兼容。

## 9. 预计影响范围

采用推荐方案 A 时，预计只需要修改：

- `app/process/query/page/chat.html`
- 对应的前端渲染测试或浏览器测试

不需要修改：

- `app/rag/query/answer_output_service.py`
- `app/resources/prompts/answer_out.prompt`
- `app/api/schemas/query.py`
- `app/api/http/query_server.py`
- QueryGraphState
- MongoDB 历史数据

因此该方案不涉及数据迁移，也不改变后端接口契约，回滚时只需恢复前端文本渲染函数。

## 10. 最终建议

本问题的根因是展示层使用 `textContent`，不是 WebSearch、Reranker 或答案模型缺少 URL。

建议保持现有 `[网络搜索/url]` 后端格式，在聊天页统一答案渲染入口中：

1. 只识别完整的 HTTP/HTTPS Web 来源标签；
2. 使用 DOM API 创建安全链接；
3. 链接在新标签页打开并设置 `noopener noreferrer`；
4. 不使用原始 `innerHTML`；
5. 流式未完成标签先按文本显示，完整后再转换；
6. 本地来源继续作为普通文本展示。

这是当前代码基础上范围最小、兼容性最好、安全边界最清晰的实现方式。

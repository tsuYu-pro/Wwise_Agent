# -*- coding: utf-8 -*-
"""
Internationalization (i18n) — 双语支持 (中文 / English)

Wwise Agent 专用翻译字典。

使用方式:
    from wwise_agent.ui.i18n import tr, set_language, get_language

    label.setText(tr("confirm"))        # -> "确认" or "Confirm"
    msg = tr("toast.undo_all", 5)       # -> "已撤销全部 5 个操作" or "Undone all 5 operations"
"""

from wwise_agent.qt_compat import QtCore, QSettings

# ---------------------------------------------------------------------------
# 全局状态
# ---------------------------------------------------------------------------
_current_lang = 'zh'  # 'zh' | 'en'

# 语言变更通知（供 retranslateUi 使用）
class _LangSignals(QtCore.QObject):
    changed = QtCore.Signal(str)   # 新语言代码

language_changed = _LangSignals()


def get_language() -> str:
    return _current_lang


def set_language(lang: str, persist: bool = True):
    """切换全局语言  lang: 'zh' | 'en'"""
    global _current_lang
    lang = lang.lower()
    if lang not in ('zh', 'en'):
        lang = 'zh'
    if lang == _current_lang:
        return
    _current_lang = lang
    if persist:
        s = QSettings("WwiseAgent", "Settings")
        s.setValue("language", lang)
    language_changed.changed.emit(lang)


def load_language():
    """启动时从 QSettings 恢复语言"""
    global _current_lang
    s = QSettings("WwiseAgent", "Settings")
    saved = s.value("language", "zh")
    if saved in ('zh', 'en'):
        _current_lang = saved


def tr(key: str, *args) -> str:
    """翻译函数  tr("key")  or  tr("key", arg1, arg2, ...)"""
    table = _ZH if _current_lang == 'zh' else _EN
    text = table.get(key)
    if text is None:
        # fallback: 尝试另一语言
        text = (_EN if _current_lang == 'zh' else _ZH).get(key, key)
    if args:
        try:
            text = text.format(*args)
        except (IndexError, KeyError):
            pass
    return text


# ---------------------------------------------------------------------------
# 翻译字典  —  按模块 / 功能分组（Wwise 版本）
# ---------------------------------------------------------------------------

_ZH = {
    # ===== Header =====
    'header.think.tooltip': '启用思考模式：AI 会先分析再回答，并显示思考过程',
    'header.cache.tooltip': '缓存管理：保存/加载对话历史',
    'header.optimize.tooltip': 'Token 优化：自动压缩和优化',
    'header.update.tooltip': '检查并更新到最新版本',
    'header.font.tooltip': '字体大小 (Ctrl+/Ctrl-)',
    'header.token_stats.tooltip': '点击查看详细 Token 统计',

    # ===== Input Area =====
    'mode.tooltip': 'Agent: AI 自主操作 Wwise 对象\nAsk: 只读查询分析',
    'confirm': '确认',
    'confirm.tooltip': '确认模式：执行修改操作前先预览确认',
    'placeholder': '输入消息... (Enter 发送, Shift+Enter 换行)',
    'attach_image.tooltip': '添加图片附件（支持 PNG/JPG/GIF/WebP，也可直接粘贴/拖拽图片到输入框）',
    'train.tooltip': '导出当前对话为训练数据（用于大模型微调）',

    # ===== Session Manager =====
    'session.new': '新建对话',
    'session.close': '关闭此对话',
    'session.close_others': '关闭其他对话',

    # ===== Font Settings =====
    'font.title': '字体大小',
    'font.scale': '字体缩放',
    'font.reset': '重置 100%',
    'font.close': '关闭',

    # ===== Thinking =====
    'thinking.init': '思考中...',
    'thinking.progress': '思考中... ({})',
    'thinking.round': '--- 第 {} 轮思考 ---',
    'thinking.done': '思考过程 ({})',

    # ===== Execution =====
    'exec.running': '执行中...',
    'exec.progress': '执行中... ({}/{})',
    'exec.done': '执行完成 ({}个操作, {})',
    'exec.done_err': '执行完成 ({} ok, {} err, {})',
    'exec.tool': '执行: {}',

    # ===== Buttons (shared) =====
    'btn.copy': '复制',
    'btn.copied': '已复制',
    'btn.close': '关闭',
    'btn.undo': 'undo',
    'btn.keep': 'keep',

    # ===== Expand / Collapse =====
    'msg.expand': '▶ 展开 ({} 行更多)',
    'msg.collapse': '▼ 收起',

    # ===== Code Preview =====
    'code.writing': '✍ Writing code for {}...',
    'code.complete': '✓ Code complete',

    # ===== Diff =====
    'diff.old': '旧值',
    'diff.new': '新值',

    # ===== Confirm Preview =====
    'confirm.title': '确认执行: {}',
    'confirm.params_more': '... 共 {} 个参数',
    'confirm.cancel': '✕ 取消',
    'confirm.execute': '↵ 确认执行',

    # ===== Wwise Object Operations =====
    'node.click_jump': '点击查看: {}',
    'status.undone': '已撤销',
    'status.kept': '已保留',

    # ===== Status / Response =====
    'status.thinking': '思考',
    'status.calls': '{}次调用',
    'status.done': '完成 ({})',
    'status.exec_done_see_above': '执行完成，详见上方执行过程。',
    'status.history': '历史',
    'status.history_summary': '历史摘要',
    'status.context': '上下文',
    'status.history_with': '历史 | {}',
    'status.stats_reset': '统计已重置',

    # ===== Image =====
    'img.preview': '图片预览',
    'img.close': '关闭',
    'img.click_zoom': '点击放大查看',
    'img.not_supported': '不支持图片',
    'img.not_supported_msg': '当前模型 {} 不支持图片输入。\n请切换至支持视觉的模型（如 Claude、GPT-5.2 等）。',
    'img.select': '选择图片',
    'img.load_failed': '加载图片失败: {}',

    # ===== Token Stats =====
    'token.title': 'Token 使用分析',
    'token.headers': ['#', '时间', '模型', 'Input', 'Cache读', 'Cache写', 'Output', 'Think', 'Total', '延迟', '费用', ''],
    'token.reset': '重置统计',
    'token.close': '关闭',
    'token.detail_title': '  请求详细 ({} calls)',
    'token.no_records': '  暂无 API 调用记录',
    'token.summary': (
        '累计统计 ({} 次请求)\n'
        '输入: {:,}\n'
        '输出: {:,}\n'
        '{}'
        'Cache 读取: {:,}\n'
        'Cache 写入: {:,}\n'
        'Cache 命中率: {}\n'
        '总计: {:,}\n'
        '预估费用: {}\n'
        '点击查看详情'
    ),
    'token.reasoning_line': '推理 Token: {:,}\n',

    # ===== Code Block =====
    'codeblock.copy': '复制',
    'codeblock.copied': '已复制',

    # ===== Toast Messages =====
    'toast.undone': '已撤销',
    'toast.undo_failed': '撤销失败: {}',
    'toast.undo_all': '已撤销全部 {} 个操作',
    'toast.keep_all': '已保留全部 {} 个操作',

    # ===== Batch Bar =====
    'batch.count': '{} 个操作待确认',

    # ===== Export Training Data =====
    'export.title': '导出训练数据',
    'export.failed': '导出失败',
    'export.error': '导出错误',
    'export.no_history': '当前没有对话记录可导出',
    'export.no_user_msg': '对话中没有用户消息',
    'export.info': '当前对话包含 {} 条用户消息，{} 条 AI 回复。\n\n选择导出方式：',
    'export.split': '分割模式',
    'export.full': '完整模式',
    'export.cancel': '取消',
    'export.done': '训练数据已导出',
    'export.success': (
        '成功导出训练数据！\n\n'
        '文件: {}\n'
        '训练样本数: {}\n'
        '对话轮次: {}\n'
        '导出模式: {}\n\n'
        '提示: 文件为 JSONL 格式，可直接用于 OpenAI/DeepSeek 微调'
    ),
    'export.mode_split': '分割模式',
    'export.mode_full': '完整模式',
    'export.open_folder': '导出成功',
    'export.open_folder_msg': '共导出 {} 条训练数据\n\n是否打开文件夹？',

    # ===== Cache =====
    'cache.archive': '存档当前对话',
    'cache.load': '加载对话...',
    'cache.compress': '压缩旧对话为摘要',
    'cache.list': '查看所有缓存',
    'cache.auto_on': '[on] 自动保存',
    'cache.auto_off': '自动保存',
    'cache.no_history': '没有对话历史可存档',
    'cache.error': '存档失败: {}',
    'cache.invalid': '缓存文件格式无效',
    'cache.no_files': '没有找到缓存文件',
    'cache.select_title': '选择缓存文件',
    'cache.file_list_title': '缓存文件列表',
    'cache.too_short': '对话历史太短，无需压缩',
    'cache.load_error': '加载缓存失败: {}',
    'cache.archived': '已存档: {} (~{} tokens)',
    'cache.loaded': '缓存已加载: {}',
    'cache.confirm_load': '确认加载',
    'cache.confirm_load_msg': '将在新标签页打开 {} 条对话记录。\n是否继续？',
    'cache.select_file': '选择要加载的缓存文件:',
    'cache.btn_load': '加载',
    'cache.btn_cancel': '取消',
    'cache.file_list': '缓存文件列表:\n',
    'cache.session_id': '   会话ID: {}',
    'cache.msg_count': '   消息数: {}',
    'cache.est_tokens': '   估计Token: ~{:,}',
    'cache.created_at': '   创建时间: {}',
    'cache.file_size': '   文件大小: {:.1f} KB',
    'cache.read_err': '[err] {} (读取失败: {})',
    'cache.btn_close': '关闭',
    'cache.msgs': '{} 条消息',

    # ===== Compress =====
    'compress.confirm_title': '确认压缩',
    'compress.confirm_msg': '将前 {} 条对话压缩为摘要，保留最近 4 轮完整对话。\n\n这可以大幅减少 token 消耗。是否继续？',
    'compress.done_title': '压缩完成',
    'compress.done_msg': '对话已压缩！\n\n原始: ~{} tokens\n压缩后: ~{} tokens\n节省: ~{} tokens ({:.1f}%)',
    'compress.summary_header': '[历史对话摘要 - 已压缩以节省 token]',
    'compress.user_reqs': '\n用户请求 ({} 条):',
    'compress.user_more': '  ... 另有 {} 条请求',
    'compress.ai_results': '\nAI 完成的任务 ({} 项):',
    'compress.ai_more': '  ... 另有 {} 项成果',

    # ===== Optimize =====
    'opt.compress_now': '立即压缩对话',
    'opt.auto_on': '自动压缩 [on]',
    'opt.auto_off': '自动压缩',
    'opt.strategy': '压缩策略',
    'opt.aggressive': '激进 (最省空间)',
    'opt.balanced': '平衡 (推荐)',
    'opt.conservative': '保守 (保留细节)',
    'opt.too_short': '对话历史太短，无需优化',
    'opt.done_title': '优化完成',
    'opt.done_msg': '对话已优化！\n\n原始: ~{:,} tokens\n优化后: ~{:,} tokens\n节省: ~{:,} tokens ({:.1f}%)\n\n压缩了 {} 条消息，保留 {} 条',
    'opt.no_need': '无需优化，对话历史已经很精简',
    'opt.auto_status': '上下文前优化: 节省 {:,} tokens (Cursor 级)',

    # ===== Update =====
    'update.checking': '检查中…',
    'update.failed_title': '检查更新',
    'update.failed_msg': '检查更新失败:\n{}',
    'update.latest_title': '检查更新',
    'update.latest_msg': '已经是最新版本！\n\n本地版本: v{}\n最新 Release: v{}',
    'update.new_title': '发现新版本',
    'update.new_msg': '发现新版本 v{}，是否立即更新？\n\n{}',
    'update.detail': '本地版本: v{}\n最新 Release: v{}',
    'update.detail_name': '\n版本名称: {}',
    'update.detail_notes': '\n更新说明: {}',
    'update.progress_title': '更新 Wwise Agent',
    'update.progress_cancel': '取消',
    'update.progress_downloading': '正在下载更新…',
    'update.downloading': '正在下载…',
    'update.extracting': '正在解压…',
    'update.applying': '正在更新文件…',
    'update.done': '更新完成！',
    'update.fail_title': '更新失败',
    'update.fail_msg': '更新过程中出现错误:\n{}',
    'update.success_title': '更新成功',
    'update.success_msg': '已成功更新 {} 个文件！\n\n点击 OK 立即重启插件。',
    'update.new_ver': '🔄 v{}',
    'update.new_ver_tip': '发现新版本 v{}，点击更新',
    'update.restart_fail_title': '重启失败',
    'update.restart_fail_msg': '自动重启失败，请手动关闭并重新打开插件。\n\n错误: {}',

    # ===== Agent Runner - Ask Mode =====
    'ask.restricted': "[Ask 模式] 工具 '{}' 不可用。当前为只读模式，无法执行修改操作。请切换到 Agent 模式。",
    'ask.user_cancel': '用户取消了 {} 操作。请理解用户的意图，继续查询或与用户沟通。',

    # ===== Agent Runner - Title =====
    'title_gen.system_zh': '你是一个标题生成器。根据对话内容生成一个简短的中文标题（≤10个字），只输出标题本身，不要引号、句号或其他多余内容。',
    'title_gen.system_en': 'Generate a short title (≤6 words) for the conversation. Output only the title itself, no quotes or punctuation.',
    'title_gen.ctx': '用户: {}\nAI: {}',

    # ===== Misc AI Tab =====
    'ai.token_limit': '\n\n[内容已达到 token 限制，已停止]',
    'ai.token_limit_status': '内容达到 token 限制，已停止',
    'ai.fake_tool': '检测到AI伪造工具调用，已自动清除',
    'ai.approaching_limit': '输出接近上限: {}/{} tokens',
    'ai.tool_result': '[工具结果] {}: {}',
    'ai.context_reminder': '[上下文提醒] {}',
    'ai.old_rounds': '[较早的工具] 已裁剪 {} 轮较旧对话以节省空间。',
    'ai.auto_opt': '上下文前优化: 节省 {:,} tokens (Cursor 级)',
    'ai.tool_exec_err': '工具执行异常: {}',
    'ai.bg_exec_err': '后台执行异常: {}',
    'ai.unknown_err': '未知错误',
    'ai.ask_mode_prompt': (
        '\n\n当前为 Ask 模式（只读）\n'
        '你只能查询、分析和回答问题。严禁执行以下操作：\n'
        '- 创建对象（create_object, create_event）\n'
        '- 删除对象（delete_object）\n'
        '- 修改属性（set_property）\n'
        '- 修改总线（assign_bus）\n'
        '- 移动对象（move_object）\n'
        '- RTPC 绑定（set_rtpc_binding）\n'
        '- 添加/移除效果器（add_effect, remove_effect）\n'
        '- 执行原始 WAAPI（execute_waapi）\n'
        '如果用户的请求需要修改操作，礼貌地说明当前处于 Ask（只读）模式，\n'
        '并建议用户切换到 Agent 模式来执行修改。\n'
        '请仅使用查询工具，如 get_project_hierarchy, get_object_properties, '
        'search_objects 等，来分析并提供建议。'
    ),
    'ai.detected_url': '\n\n[检测到 URL，将使用 fetch_webpage 获取内容：\n{}]',
    'ai.no_content': '(工具调用完成)',
    'ai.image_msg': '[图片消息]',
    'ai.glm_name': 'GLM（智谱AI）',

    # ===== History rendering =====
    'history.compressed': '[较早的工具] 已裁剪 {} 轮较旧对话执行。',
    'history.summary_title': '历史对话摘要',

    # ===== Memory System (Brain-inspired) =====
    'memory.stats': '记忆: {} 情景, {} 语义规则, {} 策略',
    'memory.reflected': '反射完成: 提取 {} 条语义规则',
    'memory.reward': '奖励引擎: reward={:.2f}, 重要性已更新',
    'memory.growth': '成长: {} 领域经验+1, 成长分={:.2f}',
    'memory.personality': '人格特征已更新',
    'memory.activated': '激活 {} 条相关记忆',
    'memory.deep_reflection': '触发深度反思 (第{}次)',
    'memory.init_done': '记忆系统初始化完成',
    'memory.init_failed': '记忆系统初始化失败: {}',
}


_EN = {
    # ===== Header =====
    'header.think.tooltip': 'Thinking mode: AI analyzes first, then answers with visible thought process',
    'header.cache.tooltip': 'Cache: Save/load conversation history',
    'header.optimize.tooltip': 'Token optimization: Auto compress and optimize',
    'header.update.tooltip': 'Check for updates',
    'header.font.tooltip': 'Font Size (Ctrl+/Ctrl-)',
    'header.token_stats.tooltip': 'Click for detailed token statistics',

    # ===== Input Area =====
    'mode.tooltip': 'Agent: AI autonomously operates Wwise objects\nAsk: Read-only query & analysis',
    'confirm': 'Confirm',
    'confirm.tooltip': 'Confirm mode: Preview before executing modifications',
    'placeholder': 'Type a message... (Enter to send, Shift+Enter for newline)',
    'attach_image.tooltip': 'Attach image (PNG/JPG/GIF/WebP, or paste/drag into input)',
    'train.tooltip': 'Export conversation as training data (for LLM fine-tuning)',

    # ===== Session Manager =====
    'session.new': 'New Chat',
    'session.close': 'Close this chat',
    'session.close_others': 'Close other chats',

    # ===== Font Settings =====
    'font.title': 'Font Size',
    'font.scale': 'Font Scale',
    'font.reset': 'Reset 100%',
    'font.close': 'Close',

    # ===== Thinking =====
    'thinking.init': 'Thinking...',
    'thinking.progress': 'Thinking... ({})',
    'thinking.round': '--- Round {} ---',
    'thinking.done': 'Thought process ({})',

    # ===== Execution =====
    'exec.running': 'Executing...',
    'exec.progress': 'Executing... ({}/{})',
    'exec.done': 'Done ({} ops, {})',
    'exec.done_err': 'Done ({} ok, {} err, {})',
    'exec.tool': 'Exec: {}',

    # ===== Buttons (shared) =====
    'btn.copy': 'Copy',
    'btn.copied': 'Copied',
    'btn.close': 'Close',
    'btn.undo': 'undo',
    'btn.keep': 'keep',

    # ===== Expand / Collapse =====
    'msg.expand': '▶ Expand ({} more lines)',
    'msg.collapse': '▼ Collapse',

    # ===== Code Preview =====
    'code.writing': '✍ Writing code for {}...',
    'code.complete': '✓ Code complete',

    # ===== Diff =====
    'diff.old': 'Old',
    'diff.new': 'New',

    # ===== Confirm Preview =====
    'confirm.title': 'Confirm: {}',
    'confirm.params_more': '... {} params total',
    'confirm.cancel': '✕ Cancel',
    'confirm.execute': '↵ Confirm',

    # ===== Wwise Object Operations =====
    'node.click_jump': 'Click to view: {}',
    'status.undone': 'Undone',
    'status.kept': 'Kept',

    # ===== Status / Response =====
    'status.thinking': 'think',
    'status.calls': '{} calls',
    'status.done': 'Done ({})',
    'status.exec_done_see_above': 'Execution complete. See the process above.',
    'status.history': 'History',
    'status.history_summary': 'History summary',
    'status.context': 'Context',
    'status.history_with': 'History | {}',
    'status.stats_reset': 'Stats reset',

    # ===== Image =====
    'img.preview': 'Image Preview',
    'img.close': 'Close',
    'img.click_zoom': 'Click to zoom',
    'img.not_supported': 'Image Not Supported',
    'img.not_supported_msg': 'Model {} does not support image input.\nPlease switch to a vision model (e.g. Claude, GPT-5.2).',
    'img.select': 'Select Image',
    'img.load_failed': 'Failed to load image: {}',

    # ===== Token Stats =====
    'token.title': 'Token Analytics',
    'token.headers': ['#', 'Time', 'Model', 'Input', 'Cache R', 'Cache W', 'Output', 'Think', 'Total', 'Latency', 'Cost', ''],
    'token.reset': 'Reset Stats',
    'token.close': 'Close',
    'token.detail_title': '  Request Details ({} calls)',
    'token.no_records': '  No API call records yet',
    'token.summary': (
        'Cumulative Stats ({} requests)\n'
        'Input: {:,}\n'
        'Output: {:,}\n'
        '{}'
        'Cache Read: {:,}\n'
        'Cache Write: {:,}\n'
        'Cache Hit Rate: {}\n'
        'Total: {:,}\n'
        'Est. Cost: {}\n'
        'Click for details'
    ),
    'token.reasoning_line': 'Reasoning Tokens: {:,}\n',

    # ===== Code Block =====
    'codeblock.copy': 'Copy',
    'codeblock.copied': 'Copied',

    # ===== Toast Messages =====
    'toast.undone': 'Undone',
    'toast.undo_failed': 'Undo failed: {}',
    'toast.undo_all': 'Undone all {} operations',
    'toast.keep_all': 'Kept all {} operations',

    # ===== Batch Bar =====
    'batch.count': '{} operations pending',

    # ===== Export Training Data =====
    'export.title': 'Export Training Data',
    'export.failed': 'Export Failed',
    'export.error': 'Export Error',
    'export.no_history': 'No conversation history to export',
    'export.no_user_msg': 'No user messages in conversation',
    'export.info': 'Conversation contains {} user messages and {} AI replies.\n\nChoose export mode:',
    'export.split': 'Split Mode',
    'export.full': 'Full Mode',
    'export.cancel': 'Cancel',
    'export.done': 'Training data exported',
    'export.success': (
        'Training data exported successfully!\n\n'
        'File: {}\n'
        'Samples: {}\n'
        'Turns: {}\n'
        'Mode: {}\n\n'
        'Tip: JSONL format, directly usable for OpenAI/DeepSeek fine-tuning'
    ),
    'export.mode_split': 'Split Mode',
    'export.mode_full': 'Full Mode',
    'export.open_folder': 'Export Successful',
    'export.open_folder_msg': 'Exported {} training samples\n\nOpen folder?',

    # ===== Cache =====
    'cache.archive': 'Archive current chat',
    'cache.load': 'Load chat...',
    'cache.compress': 'Compress old chats to summary',
    'cache.list': 'View all caches',
    'cache.auto_on': '[on] Auto save',
    'cache.auto_off': 'Auto save',
    'cache.no_history': 'No conversation history to archive',
    'cache.error': 'Archive failed: {}',
    'cache.invalid': 'Invalid cache file format',
    'cache.no_files': 'No cache files found',
    'cache.select_title': 'Select Cache File',
    'cache.file_list_title': 'Cache File List',
    'cache.too_short': 'Conversation too short to compress',
    'cache.load_error': 'Failed to load cache: {}',
    'cache.archived': 'Archived: {} (~{} tokens)',
    'cache.loaded': 'Cache loaded: {}',
    'cache.confirm_load': 'Confirm Load',
    'cache.confirm_load_msg': 'Open {} messages in a new tab.\nContinue?',
    'cache.select_file': 'Select a cache file to load:',
    'cache.btn_load': 'Load',
    'cache.btn_cancel': 'Cancel',
    'cache.file_list': 'Cache files:\n',
    'cache.session_id': '   Session ID: {}',
    'cache.msg_count': '   Messages: {}',
    'cache.est_tokens': '   Est. Tokens: ~{:,}',
    'cache.created_at': '   Created: {}',
    'cache.file_size': '   Size: {:.1f} KB',
    'cache.read_err': '[err] {} (read failed: {})',
    'cache.btn_close': 'Close',
    'cache.msgs': '{} messages',

    # ===== Compress =====
    'compress.confirm_title': 'Confirm Compression',
    'compress.confirm_msg': 'Compress the first {} messages into a summary, keeping the last 4 rounds.\n\nThis significantly reduces token usage. Continue?',
    'compress.done_title': 'Compression Complete',
    'compress.done_msg': 'Conversation compressed!\n\nOriginal: ~{} tokens\nCompressed: ~{} tokens\nSaved: ~{} tokens ({:.1f}%)',
    'compress.summary_header': '[Conversation Summary - Compressed to save tokens]',
    'compress.user_reqs': '\nUser Requests ({} total):',
    'compress.user_more': '  ... {} more requests',
    'compress.ai_results': '\nAI Completed Tasks ({} total):',
    'compress.ai_more': '  ... {} more results',

    # ===== Optimize =====
    'opt.compress_now': 'Compress conversation now',
    'opt.auto_on': 'Auto compress [on]',
    'opt.auto_off': 'Auto compress',
    'opt.strategy': 'Compression Strategy',
    'opt.aggressive': 'Aggressive (max savings)',
    'opt.balanced': 'Balanced (recommended)',
    'opt.conservative': 'Conservative (keep details)',
    'opt.too_short': 'Conversation too short to optimize',
    'opt.done_title': 'Optimization Complete',
    'opt.done_msg': 'Conversation optimized!\n\nOriginal: ~{:,} tokens\nOptimized: ~{:,} tokens\nSaved: ~{:,} tokens ({:.1f}%)\n\nCompressed {} messages, kept {}',
    'opt.no_need': 'No optimization needed, conversation is already concise',
    'opt.auto_status': 'Pre-context optimization: saved {:,} tokens (Cursor-level)',

    # ===== Update =====
    'update.checking': 'Checking…',
    'update.failed_title': 'Check Update',
    'update.failed_msg': 'Failed to check for updates:\n{}',
    'update.latest_title': 'Check Update',
    'update.latest_msg': 'Already up to date!\n\nLocal: v{}\nLatest Release: v{}',
    'update.new_title': 'New Version Available',
    'update.new_msg': 'New version v{} available. Update now?\n\n{}',
    'update.detail': 'Local: v{}\nLatest Release: v{}',
    'update.detail_name': '\nRelease: {}',
    'update.detail_notes': '\nNotes: {}',
    'update.progress_title': 'Updating Wwise Agent',
    'update.progress_cancel': 'Cancel',
    'update.progress_downloading': 'Downloading update…',
    'update.downloading': 'Downloading…',
    'update.extracting': 'Extracting…',
    'update.applying': 'Updating files…',
    'update.done': 'Update complete!',
    'update.fail_title': 'Update Failed',
    'update.fail_msg': 'Error during update:\n{}',
    'update.success_title': 'Update Successful',
    'update.success_msg': 'Successfully updated {} files!\n\nClick OK to restart the plugin.',
    'update.new_ver': '🔄 v{}',
    'update.new_ver_tip': 'New version v{} available. Click to update',
    'update.restart_fail_title': 'Restart Failed',
    'update.restart_fail_msg': 'Auto-restart failed. Please manually close and reopen the plugin.\n\nError: {}',

    # ===== Agent Runner - Ask Mode =====
    'ask.restricted': "[Ask Mode] Tool '{}' is not available. Read-only mode cannot perform modifications. Switch to Agent mode.",
    'ask.user_cancel': 'User cancelled {}. Please understand the user intent and continue querying or communicating.',

    # ===== Agent Runner - Title =====
    'title_gen.system_zh': '你是一个标题生成器。根据对话内容生成一个简短的中文标题（≤10个字），只输出标题本身，不要引号、句号或其他多余内容。',
    'title_gen.system_en': 'Generate a short title (≤6 words) for the conversation. Output only the title itself, no quotes or punctuation.',
    'title_gen.ctx': 'User: {}\nAI: {}',

    # ===== Misc AI Tab =====
    'ai.token_limit': '\n\n[Content reached token limit, stopped]',
    'ai.token_limit_status': 'Content reached token limit, stopped',
    'ai.fake_tool': 'Detected AI fake tool call, auto-cleaned',
    'ai.approaching_limit': 'Output approaching limit: {}/{} tokens',
    'ai.tool_result': '[Tool Result] {}: {}',
    'ai.context_reminder': '[Context Reminder] {}',
    'ai.old_rounds': '[Older tools] Trimmed {} older rounds to save space.',
    'ai.auto_opt': 'Pre-context optimization: saved {:,} tokens (Cursor-level)',
    'ai.tool_exec_err': 'Tool execution error: {}',
    'ai.bg_exec_err': 'Background execution error: {}',
    'ai.unknown_err': 'Unknown error',
    'ai.ask_mode_prompt': (
        '\n\nYou are in Ask mode (read-only).\n'
        'You can only query, analyze, and answer questions. Strictly forbidden operations:\n'
        '- Create objects (create_object, create_event)\n'
        '- Delete objects (delete_object)\n'
        '- Modify properties (set_property)\n'
        '- Modify buses (assign_bus)\n'
        '- Move objects (move_object)\n'
        '- RTPC bindings (set_rtpc_binding)\n'
        '- Add/remove effects (add_effect, remove_effect)\n'
        '- Execute raw WAAPI (execute_waapi)\n'
        'If the user requests modifications, politely explain you are in Ask (read-only) mode,\n'
        'and suggest switching to Agent mode to perform modifications.\n'
        'Use only query tools like get_project_hierarchy, get_object_properties, '
        'search_objects, etc., to analyze and provide suggestions.'
    ),
    'ai.detected_url': '\n\n[URL detected, will use fetch_webpage to retrieve content:\n{}]',
    'ai.no_content': '(Tool calls completed)',
    'ai.image_msg': '[Image message]',
    'ai.glm_name': 'GLM (Zhipu AI)',

    # ===== History rendering =====
    'history.compressed': '[Older tools] Trimmed {} older execution rounds.',
    'history.summary_title': 'Conversation summary',

    # ===== Memory System (Brain-inspired) =====
    'memory.stats': 'Memory: {} episodic, {} semantic rules, {} strategies',
    'memory.reflected': 'Reflection done: extracted {} semantic rules',
    'memory.reward': 'Reward engine: reward={:.2f}, importance updated',
    'memory.growth': 'Growth: {} domain exp+1, growth_score={:.2f}',
    'memory.personality': 'Personality traits updated',
    'memory.activated': 'Activated {} relevant memories',
    'memory.deep_reflection': 'Triggered deep reflection (#{} )',
    'memory.init_done': 'Memory system initialized',
    'memory.init_failed': 'Memory system init failed: {}',
}

# 启动时自动恢复语言设置
load_language()

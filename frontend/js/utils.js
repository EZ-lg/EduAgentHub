/**
 * 工具函数
 */
window.Utils = {
    /**
     * 格式化 ISO 日期为可读字符串
     */
    formatDate(isoStr, withTime = false) {
        if (!isoStr) return '';
        const d = new Date(isoStr);
        if (isNaN(d.getTime())) return '';  // 非法日期避免输出 "NaN-NaN-NaN"
        const pad = n => String(n).padStart(2, '0');
        const date = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
        if (withTime) {
            return `${date} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
        }
        return date;
    },

    /**
     * 获取当前 ISO 时间字符串
     */
    nowISO() {
        return new Date().toISOString();
    },

    /**
     * 学科名称 → emoji 图标
     */
    subjectIcon(name) {
        const map = {
            '数学': 'icon-calculator', '英语': 'icon-languages', '物理': 'icon-zap', '化学': 'icon-flask-conical',
            '语文': 'icon-book', '生物': 'icon-dna', '历史': 'icon-landmark', '地理': 'icon-globe',
            '政治': 'icon-scale', '其他': 'icon-book-open'
        };
        return map[name] || 'icon-book-open';
    },

    /**
     * 状态标签文字和颜色
     */
    statusLabel(status) {
        const map = {
            'active': { text: '在读', cls: 'badge badge--success' },
            'completed': { text: '已结课', cls: 'badge badge--neutral' },
            'abandoned': { text: '已放弃', cls: 'badge badge--danger' },
            'paused': { text: '已停用', cls: 'badge badge--warning' },
            'in_progress': { text: '进行中', cls: 'badge badge--info' },
            'draft': { text: '草稿', cls: 'badge badge--neutral' },
            'published': { text: '已发布', cls: 'badge badge--success' },
        };
        return map[status] || { text: status, cls: 'badge badge--neutral' };
    },

    /**
     * 防抖
     */
    debounce(fn, delay = 300) {
        let timer;
        return function (...args) {
            clearTimeout(timer);
            timer = setTimeout(() => fn.apply(this, args), delay);
        };
    },

    /**
     * HTML 转义
     */
    escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    },

    /**
     * 学科预设列表（F11.5 学科选项管理未做前先硬编码）
     */
    subjectPresets: ['数学', '英语', '物理', '化学', '语文', '生物', '历史', '地理', '政治', '其他'],

    /**
     * 年级选项（小学/初中/高中）
     */
    // 年级选项：统一为数据库实际存储的写法（六年级，而非小六），保证编辑时 select 能匹配预填
    grades: ['小一', '小二', '小三', '小四', '小五', '六年级', '初一', '初二', '初三', '高一', '高二', '高三'],

    /**
     * 通用表单弹窗
     * opts: { title, subtitle, fields, values, onSubmit, width, columns }
     *   fields: [{ key, label, type: 'text'|'select'|'multi-select'|'textarea'|'number'|'password'|'date',
     *              options(select/multi-select时), required, placeholder, rows, default, section, full }]
     *   columns: 1 或 2（两列填表式）；字段设 full:true 占整行
     *   onSubmit(result): 点确定后回调，result 为 {key: value}
     */
    showModal(opts) {
        const { title = '', subtitle = '', fields = [], values = {}, onSubmit, width = 520, columns = 1, bodyHtml = null, hideOk = false, renderOn = [] } = opts;
        document.querySelector('.ta-modal-mask')?.remove();

        const mask = document.createElement('div');
        mask.className = 'ta-modal-mask';
        const panel = document.createElement('div');
        panel.className = 'ta-modal-panel';
        panel.style.width = width + 'px';
        mask.appendChild(panel);
        document.body.appendChild(mask);

        // 初始值（含 default）
        const initial = {};
        fields.forEach(f => {
            initial[f.key] = (values[f.key] !== undefined && values[f.key] !== null) ? values[f.key] : (f.default || '');
        });
        let currentValues = {};

        // 字段是否显示：showWhen {key, value} → 仅当 key 当前值 === value 时显示（如 term_type 联动）
        function fieldVisible(f) {
            if (!f.showWhen) return true;
            const cur = (currentValues[f.showWhen.key] !== undefined) ? currentValues[f.showWhen.key] : initial[f.showWhen.key];
            return String(cur) === String(f.showWhen.value);
        }

        // 从当前 DOM 收集所有字段值
        function collectValues() {
            const result = {};
            for (const f of fields) {
                const el = mask.querySelector(`[data-key="${f.key}"]`);
                if (!el) continue;
                let v = el.value;
                if (f.type === 'multi-select') v = Array.from(el.querySelectorAll('input[type="checkbox"]:checked')).map(c => c.value);
                else if (f.type === 'number') v = (v === '' || v === null) ? '' : Number(v);
                result[f.key] = v;
            }
            return result;
        }

        function fieldInputHtml(f, val) {
            let input = '';
            if (f.type === 'select') {
                const opts = (f.options || []).map(o => {
                    const ov = (typeof o === 'object') ? (o.v !== undefined ? o.v : o.value) : o;
                    const ol = (typeof o === 'object') ? (o.label !== undefined ? o.label : ov) : o;
                    const sel = String(ov) === String(val) ? 'selected' : '';
                    return `<option value="${Utils.escapeHtml(String(ov))}" ${sel}>${Utils.escapeHtml(String(ol))}</option>`;
                }).join('');
                // 若当前值不在预置选项中（如旧数据「六年级/新高一」与预设不一致），
                // 补一个承载原值的选项，避免编辑时显示空白/保存时丢值（需求3）
                const hasMatch = (f.options || []).some(o => {
                    const ov = (typeof o === 'object') ? (o.v !== undefined ? o.v : o.value) : o;
                    return String(ov) === String(val);
                });
                const extra = (!hasMatch && val !== '' && val !== null && val !== undefined)
                    ? `<option value="${Utils.escapeHtml(String(val))}" selected>${Utils.escapeHtml(String(val))}</option>`
                    : '';
                input = `<select class="w-full" data-key="${f.key}">${extra}${opts}</select>`;
            } else if (f.type === 'multi-select') {
                const cur = Array.isArray(val) ? val.map(String) : [];
                const opts = (f.options || []).map(o => {
                    const ov = (typeof o === 'object') ? (o.v !== undefined ? o.v : o.value) : o;
                    const ol = (typeof o === 'object') ? (o.label !== undefined ? o.label : ov) : o;
                    const checked = cur.includes(String(ov)) ? 'checked' : '';
                    return `<label class="flex items-center gap-1.5 text-sm text-gray-600 cursor-pointer"><input type="checkbox" value="${Utils.escapeHtml(String(ov))}" ${checked}> ${Utils.escapeHtml(String(ol))}</label>`;
                }).join('');
                input = `<div class="flex flex-wrap gap-x-4 gap-y-2" data-key="${f.key}">${opts}</div>`;
            } else if (f.type === 'textarea') {
                input = `<textarea class="w-full" rows="${f.rows || 3}" placeholder="${Utils.escapeHtml(f.placeholder || '')}" data-key="${f.key}">${Utils.escapeHtml(String(val))}</textarea>`;
            } else {
                const t = f.type === 'number' ? 'number' : (f.type === 'password' ? 'password' : (f.type === 'date' ? 'date' : (f.type === 'time' ? 'time' : 'text')));
                const minAttr = f.type === 'number' && f.min !== undefined ? ` min="${f.min}"` : '';
                input = `<input type="${t}" class="w-full" value="${Utils.escapeHtml(String(val))}" placeholder="${Utils.escapeHtml(f.placeholder || '')}" data-key="${f.key}"${minAttr}>`;
            }
            const req = f.required ? '<span class="text-red-400 ml-1">*</span>' : '';
            const span = (columns === 2 && !f.full) ? '' : ' col-span-2';
            return `<div class="mb-3${span}" data-field="${f.key}"><label class="settings-label">${Utils.escapeHtml(f.label)}${req}</label>${input}</div>`;
        }

        // 渲染（含条件字段过滤 + 联动重渲染），仅保留可见字段的分组标题
        function render() {
            const vals = collectValues();
            currentValues = vals;
            let fieldHtml = '', lastSection = '';
            for (const f of fields) {
                if (!fieldVisible(f)) continue;
                // 首屏渲染时 DOM 尚无字段，collectValues() 为空 → 必须回退到 initial（values 预填值）。
                // 之前误用 f.default，导致编辑弹窗打开时预填值被丢弃，用户需重新填写（需求3）。
                const val = (vals[f.key] !== undefined && vals[f.key] !== null) ? vals[f.key] : initial[f.key];
                if (f.section && f.section !== lastSection) {
                    fieldHtml += `<div class="col-span-2 pt-2 mb-1 text-xs font-semibold text-gray-400 uppercase tracking-wide border-b" style="border-color:#f1f5f9;">${Utils.escapeHtml(f.section)}</div>`;
                    lastSection = f.section;
                }
                fieldHtml += fieldInputHtml(f, val);
            }
            const body = bodyHtml !== null
                ? bodyHtml
                : (columns === 2 ? `<div class="grid grid-cols-2 gap-x-4">${fieldHtml}</div>` : fieldHtml);
            panel.innerHTML = `
                <div class="ta-modal-head">
                    <div>
                        <div class="font-semibold text-gray-800 text-sm">${Utils.escapeHtml(title)}</div>
                        ${subtitle ? `<div class="text-xs text-gray-400 mt-0.5">${Utils.escapeHtml(subtitle)}</div>` : ''}
                    </div>
                    <button class="text-gray-300 hover:text-gray-500 text-lg leading-none" data-close>
                        <svg class="icon icon--sm"><use href="#icon-x"/></svg>
                    </button>
                </div>
                <div class="ta-modal-body">${body}</div>
                <div class="ta-modal-foot">
                    <button class="btn-outline" data-close style="padding:7px 18px;">取消</button>
                    ${hideOk ? '' : '<button class="btn-primary" data-ok style="padding:7px 18px;">确定</button>'}
                </div>
            `;
            attach();
        }

        function attach() {
            mask.querySelectorAll('[data-close]').forEach(b => b.addEventListener('click', close));
            mask.addEventListener('mousedown', (e) => { if (e.target === mask) close(); });
            // 联动重渲染：renderOn 中的 key 变化时重建表单（保留其它字段已填值）
            for (const key of renderOn) {
                const el = mask.querySelector(`[data-key="${key}"]`);
                if (el) el.addEventListener('change', () => render());
            }
            const okBtn = mask.querySelector('[data-ok]');
            if (okBtn) okBtn.addEventListener('click', () => {
                const result = collectValues();
                for (const f of fields) {
                    const v = result[f.key];
                    const emptyArr = Array.isArray(v) && v.length === 0;
                    if (f.required && (v === '' || v === null || v === undefined || emptyArr)) {
                        showToast(`请填写「${f.label}」`, 'error');
                        return;
                    }
                }
                close();
                if (onSubmit) onSubmit(result);
            });
            mask.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && e.target.tagName !== 'TEXTAREA') {
                    // hideOk 弹窗（版本历史/预览等）没有 [data-ok]，需判空
                    mask.querySelector('[data-ok]')?.click();
                }
            });
            const first = mask.querySelector('input,select,textarea');
            if (first) setTimeout(() => first.focus(), 50);
        }

        function close() { mask.remove(); }
        render();
    },

    /**
     * 确认弹窗
     * opts: { title, message, messageHtml, danger, onOk }
     *   message      普通文本 → 自动 HTML 转义（含用户数据的删除确认必须走这里，防存储型 XSS）
     *   messageHtml  需展示 HTML（如 <br>/<b>）时传此字段，替代 message
     */
    confirmDialog(opts) {
        const { title = '确认操作', message = '', messageHtml = null, danger = false, onOk } = opts;
        document.querySelector('.ta-modal-mask')?.remove();

        const mask = document.createElement('div');
        mask.className = 'ta-modal-mask';
        mask.style.paddingTop = '30vh';

        const panel = document.createElement('div');
        panel.className = 'ta-modal-panel';
        panel.style.width = '420px';

        const bodyHtml = (messageHtml !== null) ? messageHtml : Utils.escapeHtml(message);

        panel.innerHTML = `
            <div class="ta-modal-body pt-5">
                <div class="font-semibold text-gray-800 text-sm mb-2">${Utils.escapeHtml(title)}</div>
                <div class="text-sm text-gray-500 leading-relaxed">${bodyHtml}</div>
            </div>
            <div class="ta-modal-foot">
                <button class="btn-outline" data-close style="padding:7px 18px;">取消</button>
                <button class="btn-primary" data-ok
                    style="padding:7px 18px;${danger ? 'background:#ef4444;' : ''}">确定</button>
            </div>
        `;
        mask.appendChild(panel);
        document.body.appendChild(mask);

        const close = () => mask.remove();
        mask.querySelectorAll('[data-close]').forEach(b => b.addEventListener('click', close));
        mask.addEventListener('mousedown', (e) => { if (e.target === mask) close(); });
        mask.querySelector('[data-ok]').addEventListener('click', () => { close(); if (onOk) onOk(); });
    },
};

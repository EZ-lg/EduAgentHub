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
            '数学': '📐', '英语': '📝', '物理': '⚡', '化学': '🧪',
            '语文': '📖', '生物': '🧬', '历史': '📜', '地理': '🌍',
            '政治': '⚖️', '其他': '📚'
        };
        return map[name] || '📚';
    },

    /**
     * 状态标签文字和颜色
     */
    statusLabel(status) {
        const map = {
            'active': { text: '在读', cls: 'bg-green-100 text-green-700' },
            'completed': { text: '已结课', cls: 'bg-gray-100 text-gray-600' },
            'abandoned': { text: '已放弃', cls: 'bg-red-100 text-red-600' },
            'paused': { text: '已停用', cls: 'bg-yellow-100 text-yellow-700' },
            'in_progress': { text: '进行中', cls: 'bg-blue-100 text-blue-700' },
            'draft': { text: '草稿', cls: 'bg-gray-100 text-gray-500' },
            'published': { text: '已发布', cls: 'bg-green-100 text-green-700' },
        };
        return map[status] || { text: status, cls: 'bg-gray-100 text-gray-600' };
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
    grades: ['小一', '小二', '小三', '小四', '小五', '小六', '初一', '初二', '初三', '高一', '高二', '高三'],

    /**
     * 通用表单弹窗
     * opts: { title, subtitle, fields, values, onSubmit, width, columns }
     *   fields: [{ key, label, type: 'text'|'select'|'textarea'|'number'|'password',
     *              options(select时), required, placeholder, rows, default, section, full }]
     *   columns: 1 或 2（两列填表式）；字段设 full:true 占整行
     *   onSubmit(result): 点确定后回调，result 为 {key: value}
     */
    showModal(opts) {
        const { title = '', subtitle = '', fields = [], values = {}, onSubmit, width = 520, columns = 1, bodyHtml = null, hideOk = false } = opts;
        document.querySelector('.ta-modal-mask')?.remove();

        const mask = document.createElement('div');
        mask.className = 'ta-modal-mask';
        Object.assign(mask.style, {
            position: 'fixed', inset: '0', background: 'rgba(15,23,42,0.35)',
            zIndex: 1000, display: 'flex', alignItems: 'flex-start',
            justifyContent: 'center', paddingTop: '10vh',
        });

        const panel = document.createElement('div');
        Object.assign(panel.style, {
            background: '#fff', borderRadius: '12px', width: width + 'px',
            maxWidth: '92vw', boxShadow: '0 20px 50px rgba(0,0,0,0.15)',
            overflow: 'hidden', animation: 'fadeIn 0.15s ease-out',
        });

        // 渲染字段；支持 section 分组标题、full 占整行、columns 两列
        let fieldHtml = '', lastSection = '';
        fields.forEach(f => {
            const val = (values[f.key] !== undefined && values[f.key] !== null) ? values[f.key] : (f.default || '');
            const req = f.required ? '<span class="text-red-400 ml-1">*</span>' : '';
            let input = '';
            if (f.type === 'select') {
                const opts = (f.options || []).map(o => {
                    // 选项支持 {v, label} 或 {value, label} 两种写法
                    const ov = (typeof o === 'object') ? (o.v !== undefined ? o.v : o.value) : o;
                    const ol = (typeof o === 'object') ? (o.label !== undefined ? o.label : ov) : o;
                    const sel = String(ov) === String(val) ? 'selected' : '';
                    return `<option value="${Utils.escapeHtml(String(ov))}" ${sel}>${Utils.escapeHtml(String(ol))}</option>`;
                }).join('');
                input = `<select class="w-full" data-key="${f.key}">${opts}</select>`;
            } else if (f.type === 'textarea') {
                input = `<textarea class="w-full" rows="${f.rows || 3}" placeholder="${Utils.escapeHtml(f.placeholder || '')}" data-key="${f.key}">${Utils.escapeHtml(String(val))}</textarea>`;
            } else {
                const t = f.type === 'number' ? 'number' : (f.type === 'password' ? 'password' : (f.type === 'date' ? 'date' : 'text'));
                const minAttr = f.type === 'number' && f.min !== undefined ? ` min="${f.min}"` : '';
                input = `<input type="${t}" class="w-full" value="${Utils.escapeHtml(String(val))}" placeholder="${Utils.escapeHtml(f.placeholder || '')}" data-key="${f.key}"${minAttr}>`;
            }
            const span = (columns === 2 && !f.full) ? '' : ' col-span-2';
            const sectionHtml = (f.section && f.section !== lastSection)
                ? `<div class="col-span-2 pt-2 mb-1 text-xs font-semibold text-gray-400 uppercase tracking-wide border-b" style="border-color:#f1f5f9;">${Utils.escapeHtml(f.section)}</div>`
                : '';
            lastSection = f.section || lastSection;
            fieldHtml += sectionHtml
                + `<div class="mb-3${span}"><label class="settings-label">${Utils.escapeHtml(f.label)}${req}</label>${input}</div>`;
        });

        // bodyHtml 优先（只读展示，如版本列表/预览），否则渲染 fields
        const body = bodyHtml !== null
            ? bodyHtml
            : (columns === 2 ? `<div class="grid grid-cols-2 gap-x-4">${fieldHtml}</div>` : fieldHtml);

        panel.innerHTML = `
            <div class="flex items-center justify-between px-5 py-3 border-b" style="border-color:#f1f5f9;">
                <div>
                    <div class="font-semibold text-gray-800 text-sm">${Utils.escapeHtml(title)}</div>
                    ${subtitle ? `<div class="text-xs text-gray-400 mt-0.5">${Utils.escapeHtml(subtitle)}</div>` : ''}
                </div>
                <button class="text-gray-300 hover:text-gray-500 text-lg leading-none" data-close>×</button>
            </div>
            <div class="px-5 py-4 max-h-[65vh] overflow-y-auto">${body}</div>
            <div class="flex justify-end gap-2 px-5 py-3 border-t" style="border-color:#f1f5f9;">
                <button class="btn-outline" data-close style="padding:7px 18px;">取消</button>
                ${hideOk ? '' : '<button class="btn-primary" data-ok style="padding:7px 18px;">确定</button>'}
            </div>
        `;
        mask.appendChild(panel);
        document.body.appendChild(mask);

        const close = () => mask.remove();
        mask.querySelectorAll('[data-close]').forEach(b => b.addEventListener('click', close));
        mask.addEventListener('mousedown', (e) => { if (e.target === mask) close(); });

        const okBtn = mask.querySelector('[data-ok]');
        if (okBtn) okBtn.addEventListener('click', () => {
            const result = {};
            for (const f of fields) {
                const el = mask.querySelector(`[data-key="${f.key}"]`);
                let v = el ? el.value : '';
                if (f.type === 'number') v = (v === '' || v === null) ? '' : Number(v);
                result[f.key] = v;
            }
            for (const f of fields) {
                if (f.required && (result[f.key] === '' || result[f.key] === null || result[f.key] === undefined)) {
                    showToast(`请填写「${f.label}」`, 'error');
                    return;
                }
            }
            close();
            if (onSubmit) onSubmit(result);
        });

        mask.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && e.target.tagName !== 'TEXTAREA') {
                mask.querySelector('[data-ok]').click();
            }
        });

        const first = mask.querySelector('input,select,textarea');
        if (first) setTimeout(() => first.focus(), 50);
    },

    /**
     * 确认弹窗
     * opts: { title, message, danger, onOk }
     */
    confirmDialog(opts) {
        const { title = '确认操作', message = '', danger = false, onOk } = opts;
        document.querySelector('.ta-modal-mask')?.remove();

        const mask = document.createElement('div');
        mask.className = 'ta-modal-mask';
        Object.assign(mask.style, {
            position: 'fixed', inset: '0', background: 'rgba(15,23,42,0.35)',
            zIndex: 1000, display: 'flex', alignItems: 'flex-start',
            justifyContent: 'center', paddingTop: '30vh',
        });

        const panel = document.createElement('div');
        Object.assign(panel.style, {
            background: '#fff', borderRadius: '12px', width: '420px',
            maxWidth: '92vw', boxShadow: '0 20px 50px rgba(0,0,0,0.15)',
            overflow: 'hidden', animation: 'fadeIn 0.15s ease-out',
        });

        panel.innerHTML = `
            <div class="px-5 pt-5 pb-2">
                <div class="font-semibold text-gray-800 text-sm mb-2">${Utils.escapeHtml(title)}</div>
                <div class="text-sm text-gray-500 leading-relaxed">${message}</div>
            </div>
            <div class="flex justify-end gap-2 px-5 py-3 border-t mt-2" style="border-color:#f1f5f9;">
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

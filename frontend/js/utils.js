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
};

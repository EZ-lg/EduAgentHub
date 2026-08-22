/**
 * Vue 应用入口 - 路由 + 全局状态
 */
const { createApp, ref, reactive, computed, provide, inject, onMounted, nextTick } = Vue;
const { createRouter, createWebHashHistory } = VueRouter;

// ============================================================
// 全局状态（用 reactive + provide/inject）
// ============================================================
const store = reactive({
    // 页面标题
    pageTitle: '工作台',
    // 侧边栏当前路由
    currentRoute: '/dashboard',
    // 用户信息/机构信息（从设置加载）
    orgName: 'XX教育机构',
    // Toast 消息
    toasts: [],
});

function showToast(message, type = 'info') {
    const id = Date.now();
    store.toasts.push({ id, message, type });
    setTimeout(() => {
        store.toasts = store.toasts.filter(t => t.id !== id);
    }, 3000);
}
// 暴露给页面内联脚本使用（页面模板通过 v-html 注入，不在 Vue 组件内）
window.showToast = showToast;

// ============================================================
// 页面模板缓存（fetch 加载 HTML 片段）
// ============================================================
const templateCache = {};

async function loadTemplate(name) {
    if (templateCache[name]) return templateCache[name];
    try {
        // 带版本号请求，配合后端 no-store，杜绝浏览器缓存旧页面
        const ver = window.APP_VERSION || '';
        const resp = await fetch(`/pages/${name}.html?v=${ver}`);
        if (!resp.ok) throw new Error(`Failed to load ${name}`);
        const html = await resp.text();
        templateCache[name] = html;
        return html;
    } catch (err) {
        console.error(`Template load error [${name}]:`, err);
        return `<div class="p-8 text-center text-gray-500">页面加载失败: ${name}</div>`;
    }
}

// 执行容器内所有 <script> 块
// 说明：v-html / innerHTML 注入的脚本不会被浏览器自动执行，
// 必须手动重建 script 节点才能触发。页面模板普遍依赖此机制。
function executeInlineScripts(container) {
    if (!container) return;
    container.querySelectorAll('script').forEach(oldScript => {
        const newScript = document.createElement('script');
        if (oldScript.src) {
            newScript.src = oldScript.src;
            newScript.async = true;
        } else {
            newScript.textContent = oldScript.textContent;
        }
        oldScript.replaceWith(newScript);
    });
    // 注意：不在此处无条件清除 ta_wdog —— 页面脚本是异步执行，若脚本崩溃，
    // 此处仍会执行导致「重载后再次清除」→ 看门狗无限刷新。
    // 清除时机移到看门狗逻辑中，仅当页面脚本确认正常运行后才重置。
}

// ============================================================
// 全局刷新机制
// 页面脚本末尾注册 window.currentPageRefresh（如 loadStudents），
// 顶部「↻ 刷新」按钮和切回标签页时自动调用，无需手动 F5
// ============================================================
window.refreshPage = function () {
    try { if (typeof window.currentPageRefresh === 'function') window.currentPageRefresh(); }
    catch (e) { console.error('刷新失败:', e); }
};

document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') {
        window.refreshPage();
    }
});

// 创建一个通用页面组件工厂
function createPageComponent(pageName, title) {
    return {
        template: `<div v-html="pageHtml"></div>`,
        data() {
            return { pageHtml: '<div class="text-center py-12 text-gray-400">加载中...</div>' };
        },
        async mounted() {
            store.pageTitle = title;
            this.pageHtml = await loadTemplate(pageName);
            // 触发 Vue 编译内联模板（如果页面包含 Vue 指令）
            await nextTick();
            this.$forceUpdate();
            // 执行页面内联脚本（innerHTML 不会自动执行 <script>）
            executeInlineScripts(this.$el);

            // 加载看门狗：仅当页面脚本压根没执行（加载失败/旧缓存代码）时强制刷新一次兜底。
            // 不自动刷新"活页面"：若脚本已执行（currentPageRefresh 已注册），页内"加载中"多为
            // 异步加载的临时状态（隐藏容器占位/Tab 切换瞬态），自动刷新会整页重渲染，
            // 打断用户正在输入的编辑和滚动位置（曾因此误伤学科详情的课程规划编辑）
            setTimeout(() => {
                try {
                    if (!this.$el || !this.$el.isConnected) return;
                    if (this.$el.textContent.includes('加载中')) {
                        // 页面脚本没跑起来（currentPageRefresh 未注册）且未重载过 → 强制刷新一次兜底
                        if (typeof window.currentPageRefresh !== 'function' && sessionStorage.getItem('ta_wdog') !== '1') {
                            sessionStorage.setItem('ta_wdog', '1');
                            location.reload();
                            return;
                        }
                    }
                    // 页面脚本正常运行（已注册刷新函数）→ 清除重载标记，允许下次故障再兜底一次
                    // 崩溃场景下 ta_wdog 保持 '1'，重载后仍崩溃也不会再刷（防无限整页刷新）
                    if (typeof window.currentPageRefresh === 'function') {
                        try { sessionStorage.removeItem('ta_wdog'); } catch (e) {}
                    }
                } catch (e) { console.error('看门狗异常:', e); }
            }, 6000);
        },
        unmounted() {
            // 导航离开时释放页面资源（ECharts 实例 / 全局监听器）
            // 页面脚本在 IIFE 末尾注册 window.__pageUnmounted（见 student_detail 等页面）
            try {
                if (typeof window.__pageUnmounted === 'function') window.__pageUnmounted();
            } catch (e) { console.error('页面卸载清理异常:', e); }
        },
    };
}

// ============================================================
// 路由定义
// ============================================================
const routes = [
    { path: '/', redirect: '/dashboard' },
    {
        path: '/dashboard',
        component: createPageComponent('dashboard', '工作台'),
    },
    {
        path: '/students',
        component: createPageComponent('student_list', '学生档案'),
    },
    {
        path: '/student/:id',
        component: createPageComponent('student_detail', '学生详情'),
        props: true,
    },
    {
        path: '/student/:id/subject/:sid',
        component: createPageComponent('student_detail', '学科详情'),
        props: true,
    },
    {
        path: '/conversation/:id',
        component: createPageComponent('conversation', 'AI 对话采集'),
        props: true,
    },
    {
        path: '/report/:id',
        component: createPageComponent('report', '学情报告'),
        props: true,
    },
    {
        path: '/classes',
        component: createPageComponent('classes', '班级管理'),
    },
    {
        path: '/classes/:id',
        component: createPageComponent('classes', '班级详情'),
        props: true,
    },
    {
        path: '/schedule',
        component: createPageComponent('schedule', '课表'),
    },
    {
        path: '/teachers',
        component: createPageComponent('teachers', '教师管理'),
    },
    {
        path: '/knowledge-base',
        component: createPageComponent('knowledge_base', '知识库管理'),
    },
    {
        path: '/knowledge-base/qa',
        component: createPageComponent('knowledge_qa', '知识库智能问答'),
    },
    {
        path: '/settings',
        component: createPageComponent('settings', '系统设置'),
    },
];

const router = createRouter({
    history: createWebHashHistory(),
    routes,
});

// 路由变化时更新侧边栏高亮
router.afterEach((to) => {
    store.currentRoute = to.path;
});

// ============================================================
// Toast 组件
// ============================================================
const ToastComponent = {
    template: `
        <div class="toast-container">
            <div v-for="t in store.toasts" :key="t.id"
                 :class="['toast', 'fade-in',
                          t.type === 'success' ? 'toast--success' :
                          t.type === 'error' ? 'toast--error' : 'toast--info']">
                <svg class="icon"><use :href="t.type === 'success' ? '#icon-check-circle' : t.type === 'error' ? '#icon-x-circle' : '#icon-info-circle'"/></svg>
                <span>{{ t.message }}</span>
            </div>
        </div>
    `,
    setup() { return { store }; },
};

// ============================================================
// 创建 Vue 应用
// ============================================================
const app = createApp({
    setup() {
        provide('store', store);
        provide('showToast', showToast);
        return { store };
    },
    async mounted() {
        // 注入 SVG 图标雪碧图（商用视觉重构：icons.html 定义全部 <symbol>）
        try {
            const ivec = await fetch('/components/icons.html?v=' + (window.APP_VERSION || ''));
            if (ivec.ok) {
                const itxt = await ivec.text();
                document.body.insertAdjacentHTML('afterbegin', itxt);
            }
        } catch (err) {
            console.error('Icons load error:', err);
        }
        // 加载侧边栏
        try {
            const resp = await fetch('/components/navbar.html?v=' + (window.APP_VERSION || ''));
            if (resp.ok) {
                const html = await resp.text();
                document.getElementById('navbar-container').innerHTML = html;
                // innerHTML 注入的 <script> 不会执行，必须重建脚本节点让 updateNavActive 等注册到 window
                executeInlineScripts(document.getElementById('navbar-container'));
            }
        } catch (err) {
            console.error('Navbar load error:', err);
        }
        // 加载机构名称（P9：显示在侧边栏）
        try {
            const r = await API.settings.getAll();
            const org = (r.success && r.data.org_name) || {};
            if (org.name) {
                store.orgName = org.name;
                const el = document.getElementById('navbar-org-name');
                if (el) el.textContent = org.name;
            }
        } catch (err) {
            console.error('加载机构名称失败:', err);
        }
    },
});

app.use(router);
app.component('ToastWidget', ToastComponent);
app.mount('#app');

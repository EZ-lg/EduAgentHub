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

// ============================================================
// 页面模板缓存（fetch 加载 HTML 片段）
// ============================================================
const templateCache = {};

async function loadTemplate(name) {
    if (templateCache[name]) return templateCache[name];
    try {
        const resp = await fetch(`/pages/${name}.html`);
        if (!resp.ok) throw new Error(`Failed to load ${name}`);
        const html = await resp.text();
        templateCache[name] = html;
        return html;
    } catch (err) {
        console.error(`Template load error [${name}]:`, err);
        return `<div class="p-8 text-center text-gray-500">页面加载失败: ${name}</div>`;
    }
}

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
        <div class="fixed top-4 right-4 z-50 space-y-2">
            <div v-for="t in store.toasts" :key="t.id"
                 :class="['px-4 py-3 rounded-lg shadow-lg text-sm text-white fade-in',
                          t.type === 'success' ? 'bg-green-500' :
                          t.type === 'error' ? 'bg-red-500' : 'bg-blue-500']">
                {{ t.message }}
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
        // 加载侧边栏
        try {
            const resp = await fetch('/components/navbar.html');
            if (resp.ok) {
                const html = await resp.text();
                document.getElementById('navbar-container').innerHTML = html;
            }
        } catch (err) {
            console.error('Navbar load error:', err);
        }
    },
});

app.use(router);
app.component('ToastWidget', ToastComponent);
app.mount('#app');

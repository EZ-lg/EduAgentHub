/**
 * API 封装 - 统一的 fetch 请求处理
 */
window.API = {
    BASE: '',

    async request(url, options = {}) {
        const config = {
            headers: { 'Content-Type': 'application/json' },
            ...options,
        };
        if (config.body && typeof config.body === 'object') {
            config.body = JSON.stringify(config.body);
        }
        try {
            const resp = await fetch(this.BASE + url, config);
            const json = await resp.json();
            if (!resp.ok) {
                throw new Error(json.detail || json.error || `HTTP ${resp.status}`);
            }
            return json;
        } catch (err) {
            console.error(`API Error [${url}]:`, err);
            throw err;
        }
    },

    get(url)     { return this.request(url); },
    post(url, body)   { return this.request(url, { method: 'POST', body }); },
    put(url, body)    { return this.request(url, { method: 'PUT', body }); },
    delete(url)       { return this.request(url, { method: 'DELETE' }); },

    // === 学生 ===
    students: {
        list(params = {}) {
            const qs = new URLSearchParams(params).toString();
            return API.get(`/api/students?${qs}`);
        },
        create(data) { return API.post('/api/students', data); },
        get(id)      { return API.get(`/api/students/${id}`); },
        update(id, data) { return API.put(`/api/students/${id}`, data); },
        delete(id)   { return API.delete(`/api/students/${id}`); },
        updateStatus(id, status) { return API.put(`/api/students/${id}/status`, { status }); },
    },

    // === 学科 ===
    subjects: {
        list(studentId) { return API.get(`/api/students/${studentId}/subjects`); },
        create(data)    { return API.post('/api/subjects', data); },
        get(id)         { return API.get(`/api/subjects/${id}`); },
        update(id, data) { return API.put(`/api/subjects/${id}`, data); },
        updateStatus(id, status) { return API.put(`/api/subjects/${id}/status`, { status }); },
    },

    // === AI 对话 ===
    conversations: {
        start(subjectId) { return API.post(`/api/subjects/${subjectId}/conversation/start`); },
        send(subjectId, data) { return API.post(`/api/subjects/${subjectId}/conversation/message`, data); },
        end(subjectId, data) { return API.post(`/api/subjects/${subjectId}/conversation/end`, data || {}); },
        list(subjectId) { return API.get(`/api/subjects/${subjectId}/conversations`); },
    },

    // === 报告 ===
    reports: {
        list(subjectId) { return API.get(`/api/subjects/${subjectId}/reports`); },
        generate(subjectId, data) { return API.post(`/api/subjects/${subjectId}/reports/generate`, data || {}); },
        get(id) { return API.get(`/api/reports/${id}`); },
        update(id, data) { return API.put(`/api/reports/${id}`, data); },
        regenerate(id, data) { return API.post(`/api/reports/${id}/regenerate`, data || {}); },
    },

    // === 成绩 ===
    scores: {
        list(subjectId) { return API.get(`/api/subjects/${subjectId}/scores`); },
        create(subjectId, data) { return API.post(`/api/subjects/${subjectId}/scores`, data); },
        update(id, data) { return API.put(`/api/scores/${id}`, data); },
        delete(id) { return API.delete(`/api/scores/${id}`); },
    },

    // === 课程规划 ===
    plans: {
        list(subjectId) { return API.get(`/api/subjects/${subjectId}/plans`); },
        create(subjectId, data) { return API.post(`/api/subjects/${subjectId}/plans`, data); },
        update(id, data) { return API.put(`/api/plans/${id}`, data); },
        versions(id) { return API.get(`/api/plans/${id}/versions`); },
    },

    // === 沟通日志 ===
    commLogs: {
        list(subjectId) { return API.get(`/api/subjects/${subjectId}/communication-logs`); },
        create(subjectId, data) { return API.post(`/api/subjects/${subjectId}/communication-logs`, data); },
        update(id, data) { return API.put(`/api/communication-logs/${id}`, data); },
        delete(id) { return API.delete(`/api/communication-logs/${id}`); },
    },

    // === 教师 ===
    teachers: {
        list(search = '') { return API.get(`/api/teachers?search=${search}`); },
        create(data) { return API.post('/api/teachers', data); },
        update(id, data) { return API.put(`/api/teachers/${id}`, data); },
        delete(id) { return API.delete(`/api/teachers/${id}`); },
    },

    // === 知识库 ===
    knowledgeBase: (() => {
        // /api/knowledge-docs 和 /api/knowledge/qa 两个前缀
        return {
            list(category = '') { return API.get(`/api/knowledge-docs?category=${category}`); },
            get(id) { return API.get(`/api/knowledge-docs/${id}`); },
            delete(id) { return API.delete(`/api/knowledge-docs/${id}`); },
            toggleStatus(id, status) { return API.put(`/api/knowledge-docs/${id}/status`, { status }); },
            qa(question) { return API.post('/api/knowledge/qa', { question }); },
            presets() { return API.get('/api/knowledge/qa/presets'); },
        };
    })(),

    // === 设置 ===
    settings: {
        getAll() { return API.get('/api/settings'); },
        providers() { return API.get('/api/settings/providers'); },
        update(data) { return API.put('/api/settings', data); },
        testLLM(data) { return API.post('/api/settings/test-llm', data || {}); },
        testEmbed(data) { return API.post('/api/settings/test-embed', data || {}); },
    },

    // === 工作台 ===
    dashboard: {
        stats() { return API.get('/api/dashboard/stats'); },
        activities() { return API.get('/api/dashboard/activities'); },
    },
};

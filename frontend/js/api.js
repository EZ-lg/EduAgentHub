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
        chat(id, messages) { return API.post(`/api/students/${id}/chat`, { messages }); },
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
        delete(id) { return API.delete(`/api/reports/${id}`); },
        pdf(id) { return API.get(`/api/reports/${id}/pdf`); },
    },

    // === 成绩 ===
    scores: {
        list(subjectId) { return API.get(`/api/subjects/${subjectId}/scores`); },
        create(subjectId, data) { return API.post(`/api/subjects/${subjectId}/scores`, data); },
        batch(subjectId, data) { return API.post(`/api/subjects/${subjectId}/scores/batch`, data); },
        analyze(subjectId) { return API.post(`/api/subjects/${subjectId}/scores/analyze`, {}); },
        update(id, data) { return API.put(`/api/scores/${id}`, data); },
        delete(id) { return API.delete(`/api/scores/${id}`); },
    },

    // === 课程规划 ===
    plans: {
        list(subjectId) { return API.get(`/api/subjects/${subjectId}/plans`); },
        create(subjectId, data) { return API.post(`/api/subjects/${subjectId}/plans`, data); },
        save(subjectId, data) { return API.post(`/api/subjects/${subjectId}/plans/save`, data); },
        adjust(subjectId) { return API.post(`/api/subjects/${subjectId}/plans/adjust`, {}); },
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

    // === 教室（2.0 排课资源）===
    classrooms: {
        list(status = '') { return API.get(`/api/classrooms?status=${status}`); },
        create(data) { return API.post('/api/classrooms', data); },
        update(id, data) { return API.put(`/api/classrooms/${id}`, data); },
        delete(id) { return API.delete(`/api/classrooms/${id}`); },
    },

    // === 班级（2.0 上课维度）===
    classes: {
        list(params = {}) {
            const qs = new URLSearchParams(params).toString();
            return API.get(`/api/classes?${qs}`);
        },
        get(id) { return API.get(`/api/classes/${id}`); },
        create(data) { return API.post('/api/classes', data); },
        update(id, data) { return API.put(`/api/classes/${id}`, data); },
        updateStatus(id, status) { return API.put(`/api/classes/${id}/status`, { status }); },
        delete(id) { return API.delete(`/api/classes/${id}`); },
        addStudent(id, data) { return API.post(`/api/classes/${id}/students`, data); },
        removeStudent(id, sid) { return API.delete(`/api/classes/${id}/students/${sid}`); },
        createFromSubject(subjectId, data) { return API.post(`/api/classes/from-subject/${subjectId}`, data || {}); },
        extend(id, data) { return API.post(`/api/classes/${id}/extend`, data); },
    },

    // === 排课 / 课表（2.0 P3）===
    schedules: {
        periods() { return API.get('/api/schedules/periods'); },
        updatePeriods(periods) { return API.put('/api/schedules/periods', { periods }); },
        weekly(params = {}) {
            const qs = new URLSearchParams(params).toString();
            return API.get(`/api/schedules/weekly?${qs}`);
        },
        day(date) { return API.get(`/api/schedules/day?date=${date}`); },
        autoPlan(data) { return API.post('/api/schedules/auto-plan', data); },
        confirm(data) { return API.post('/api/schedules/confirm', data); },
        check(data) { return API.post('/api/schedules/check', data); },
        add(data) { return API.post('/api/schedules', data); },
        update(id, data) { return API.put(`/api/schedules/${id}`, data); },
        delete(id) { return API.delete(`/api/schedules/${id}`); },
    },

    // === 知识库 ===
    knowledgeBase: (() => {
        // /api/knowledge-docs（管理）和 /api/knowledge（问答）两个前缀
        return {
            list(category = '') { return API.get(`/api/knowledge-docs?category=${category}`); },
            get(id) { return API.get(`/api/knowledge-docs/${id}`); },
            delete(id) { return API.delete(`/api/knowledge-docs/${id}`); },
            toggleStatus(id, status) { return API.put(`/api/knowledge-docs/${id}/status`, { status }); },
            // 文件上传走 FormData，不能带 JSON Content-Type；auto_category 由 AI 自动判断分类
            upload(category, title, file, autoCategory = false) {
                const fd = new FormData();
                fd.append('category', category || '其他');
                fd.append('title', title || '');
                fd.append('auto_category', autoCategory ? 'true' : 'false');
                fd.append('file', file);
                return fetch('/api/knowledge-docs/upload', { method: 'POST', body: fd })
                    .then(r => r.json().then(json => ({ ok: r.ok, json })))
                    .then(({ ok, json }) => {
                        if (!ok) throw new Error(json.detail || json.error || '上传失败');
                        return json;
                    });
            },
            preview(id) { return API.get(`/api/knowledge-docs/${id}/preview`); },
            reparse(id) { return API.post(`/api/knowledge-docs/${id}/reparse`, {}); },
            search(data) { return API.post('/api/knowledge-docs/search', data); },
            rebuild() { return API.post('/api/knowledge-docs/rebuild', {}); },
            qa(question) { return API.post('/api/knowledge/qa', { question }); },
            presets() { return API.get('/api/knowledge/qa/presets'); },
            qaHistory() { return API.get('/api/knowledge/qa/history'); },
            clearHistory() { return API.delete('/api/knowledge/qa/history'); },
        };
    })(),

    // === 设置 ===
    settings: {
        getAll() { return API.get('/api/settings'); },
        providers() { return API.get('/api/settings/providers'); },
        update(data) { return API.put('/api/settings', data); },
        testLLM(data) { return API.post('/api/settings/test-llm', data || {}); },
        testEmbed(data) { return API.post('/api/settings/test-embed', data || {}); },
        backup() { return API.post('/api/settings/backup'); },
        backupsList() { return API.get('/api/settings/backups'); },
    },

    // === 工作台 ===
    dashboard: {
        stats() { return API.get('/api/dashboard/stats'); },
        activities() { return API.get('/api/dashboard/activities'); },
        board() { return API.get('/api/dashboard/board'); },
        trend() { return API.get('/api/dashboard/trend'); },
        subjectDist() { return API.get('/api/dashboard/subject-dist'); },
    },

    // === 全局总览 / 学生总览（2.0 P5 G4/G5）===
    overview: {
        global() { return API.get('/api/overview'); },
        student(studentId) { return API.get(`/api/students/${studentId}/overview`); },
    },
};

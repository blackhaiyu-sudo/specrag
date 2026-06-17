window.apiBaseUrl = window.apiBaseUrl || `${window.location.origin}/api`;
var apiBaseUrl = window.apiBaseUrl;
const kbApiBase = `${apiBaseUrl}/kb/v1`;

let kbMarkedInitialized = false;

function initializeMarkedForKb() {
    if (typeof marked === 'undefined') {
        return false;
    }
    try {
        if (typeof marked.setOptions === 'function') {
            marked.setOptions({
                breaks: true,
                gfm: true
            });
        }
        kbMarkedInitialized = true;
        return true;
    } catch (error) {
        console.warn('marked 初始化失败:', error);
        return false;
    }
}

function safeRenderMarkdown(content) {
    if (!content) {
        return '';
    }
    if (!kbMarkedInitialized) {
        initializeMarkedForKb();
    }
    if (kbMarkedInitialized && typeof marked !== 'undefined') {
        try {
            if (typeof marked.parse === 'function') {
                return marked.parse(content);
            }
            if (typeof marked === 'function') {
                return marked(content);
            }
        } catch (error) {
            console.warn('Markdown 渲染失败:', error);
        }
    }
    return String(content)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/\n/g, '<br>');
}

initializeMarkedForKb();

Vue.component('result-list', {
    props: {
        items: {
            type: Array,
            default: () => []
        }
    },
    template: `
        <el-card shadow="never" class="result-card">
            <div slot="header" class="card-header">
                <span>证据来源</span>
                <span class="muted">{{ items.length }} 条</span>
            </div>
            <div v-if="items.length === 0" class="empty-line">暂无结果。</div>
            <div v-for="item in items" :key="sourceKey(item)" class="result-item">
                <div class="result-top">
                    <div class="result-title">{{ item.unit_id }} {{ item.unit_title }}</div>
                    <div class="result-tags">
                        <el-tag v-if="item.vector_type" size="mini">{{ item.vector_type }}</el-tag>
                        <el-tag v-if="item.score !== undefined && item.score !== null" size="mini" type="info">score {{ item.score }}</el-tag>
                    </div>
                </div>
                <div class="result-meta">{{ item.doc_title }} / {{ item.version || '-' }}</div>
                <div class="result-evidence">{{ item.evidence || item.content || '' }}</div>
            </div>
        </el-card>
    `,
    methods: {
        sourceKey(item) {
            return `${item.doc_id || ''}:${item.unit_id || ''}:${item.vector_type || ''}:${item.score || ''}`;
        }
    }
});

new Vue({
    el: '#kb-app',
    data() {
        return {
            activeView: 'overview',
            stats: {},
            documents: [],
            units: [],
            selectedDoc: null,
            importMode: 'createImage',
            importForm: {
                jsonPath: 'runtime/kb_query_hints/final_full/req_mod_20260512_085938.with_hints.json',
                rebuild: false
            },
            importResult: null,
            askForm: {
                question: '',
                topK: 3
            },
            answer: null,
            answerSources: [],
            askAudits: [],
            loading: {
                stats: false,
                documents: false,
                units: false,
                importing: false,
                asking: false,
                audits: false
            }
        };
    },
    computed: {
        viewTitle() {
            const titles = {
                overview: '总览',
                import: '导入知识',
                documents: '文档管理',
                ask: '问答测试'
            };
            return titles[this.activeView] || '知识库工作台';
        },
        viewSubtitle() {
            const subtitles = {
                overview: '查看当前知识库规模，快速进入导入和问答测试',
                import: '使用原文本 PRD 和图片需求模块流程导入知识库',
                documents: '查看已导入文档和知识单元',
                ask: '基于 MCP Agent 检索、判断证据并回答问题'
            };
            return subtitles[this.activeView] || '';
        },
        metrics() {
            return [
                { label: '文档', value: this.stats.documents || 0 },
                { label: '知识单元', value: this.stats.units || 0 },
                { label: '向量', value: this.stats.vectors || 0 }
            ];
        }
    },
    created() {
        this.refreshAll();
    },
    methods: {
        formatJson(value) {
            return JSON.stringify(value || {}, null, 2);
        },
        formatNumber(value) {
            const number = Number(value || 0);
            if (!Number.isFinite(number)) {
                return '0';
            }
            return number.toLocaleString('zh-CN');
        },
        formatSeconds(value) {
            const number = Number(value || 0);
            if (!Number.isFinite(number) || number <= 0) {
                return '-';
            }
            return `${number.toFixed(2)}s`;
        },
        usageStats(record) {
            return (record && record.usage_stats) || {};
        },
        tokenUsage(record) {
            const stats = this.usageStats(record);
            if (stats.token_usage) {
                return stats.token_usage;
            }
            return (record && record.usage) || {};
        },
        tokenValue(record, key) {
            const usage = this.tokenUsage(record);
            const value = usage[key];
            if (value !== undefined && value !== null) {
                return value;
            }
            if (key === 'reasoning_tokens') {
                const details = usage.completion_tokens_details || {};
                return details.reasoning_tokens || 0;
            }
            if (key === 'cached_tokens') {
                const details = usage.prompt_tokens_details || {};
                return details.cached_tokens || 0;
            }
            return 0;
        },
        usageValue(record, key) {
            const stats = this.usageStats(record);
            if (stats[key] !== undefined && stats[key] !== null) {
                return stats[key];
            }
            if (key === 'tool_call_count') {
                return ((record && (record.backend_tool_trace || record.tool_trace)) || []).length;
            }
            if (key === 'model_call_count') {
                return this.tokenValue(record, 'total_tokens') > 0 ? 1 : 0;
            }
            return 0;
        },
        answerDuration(record) {
            const stats = this.usageStats(record);
            return stats.duration_seconds || (record && record.duration_seconds) || 0;
        },
        unwrap(response) {
            const body = response && response.data ? response.data : {};
            if (body.success || body.code === 0) {
                return body.data || {};
            }
            throw new Error(body.error || '请求失败');
        },
        errorMessage(error) {
            if (error.response && error.response.data) {
                return error.response.data.error || error.response.data.message || error.message;
            }
            return error.message || String(error);
        },
        refreshAll() {
            this.loadStats();
            this.loadDocuments();
            this.loadAskAudits();
        },
        async loadStats() {
            this.loading.stats = true;
            try {
                const response = await axios.get(`${kbApiBase}/stats`);
                this.stats = this.unwrap(response);
            } catch (error) {
                this.$message.error(`加载统计失败：${this.errorMessage(error)}`);
            } finally {
                this.loading.stats = false;
            }
        },
        async loadDocuments() {
            this.loading.documents = true;
            try {
                const response = await axios.get(`${kbApiBase}/documents`);
                const data = this.unwrap(response);
                this.documents = data.documents || [];
            } catch (error) {
                this.$message.error(`加载文档失败：${this.errorMessage(error)}`);
            } finally {
                this.loading.documents = false;
            }
        },
        async importJson() {
            if (!this.importForm.jsonPath.trim()) {
                this.$message.warning('请填写 JSON 路径');
                return;
            }
            this.loading.importing = true;
            this.importResult = null;
            try {
                const response = await axios.post(`${kbApiBase}/documents/import-json`, {
                    json_path: this.importForm.jsonPath.trim(),
                    rebuild: this.importForm.rebuild
                });
                this.importResult = this.unwrap(response);
                this.$message.success('导入完成');
                this.refreshAll();
            } catch (error) {
                this.$message.error(`导入失败：${this.errorMessage(error)}`);
            } finally {
                this.loading.importing = false;
            }
        },
        async selectDocument(doc) {
            this.selectedDoc = doc;
            this.activeView = this.activeView === 'overview' ? 'documents' : this.activeView;
            await this.loadUnits(doc.doc_id);
        },
        async loadUnits(docId) {
            if (!docId) return;
            this.loading.units = true;
            try {
                const response = await axios.get(`${kbApiBase}/documents/${encodeURIComponent(docId)}/units`);
                const data = this.unwrap(response);
                this.units = data.units || [];
            } catch (error) {
                this.$message.error(`加载知识单元失败：${this.errorMessage(error)}`);
            } finally {
                this.loading.units = false;
            }
        },
        normalizeResults(results) {
            return (results || []).map(item => {
                const unit = item.unit || {};
                const source = unit.source || {};
                return {
                    doc_id: item.doc_id,
                    doc_title: item.doc_title,
                    version: item.version,
                    unit_id: item.unit_id || unit.unit_id,
                    unit_title: unit.title || item.unit_title,
                    score: item.score,
                    vector_type: item.vector_type,
                    evidence: source.evidence || item.evidence || unit.content || '',
                    content: unit.content || item.content || ''
                };
            });
        },
        async ask() {
            const question = this.askForm.question.trim();
            if (!question) {
                this.$message.warning('请输入问题');
                return;
            }
            if (this.loading.asking) {
                return;
            }
            this.loading.asking = true;
            this.answer = null;
            this.answerSources = [];
            try {
                const payload = {
                    question,
                    top_k: this.askForm.topK
                };
                const response = await axios.post(`${kbApiBase}/retrieval/agent-ask`, payload);
                const data = this.unwrap(response);
                this.answer = data;
                this.answerSources = data.sources || [];
                this.loadAskAudits();
            } catch (error) {
                this.$message.error(`问答失败：${this.errorMessage(error)}`);
            } finally {
                this.loading.asking = false;
            }
        },
        async loadAskAudits() {
            this.loading.audits = true;
            try {
                const response = await axios.get(`${kbApiBase}/retrieval/agent-ask/audits`, {
                    params: { limit: 10 }
                });
                const data = this.unwrap(response);
                this.askAudits = data.audits || [];
            } catch (error) {
                console.warn('加载问答审计失败:', this.errorMessage(error));
            } finally {
                this.loading.audits = false;
            }
        },
        setQuestion(question) {
            this.askForm.question = question;
            this.activeView = 'ask';
        }
    }
});

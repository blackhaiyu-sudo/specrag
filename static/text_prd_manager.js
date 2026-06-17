/**
 * 文本PRD管理组件
 * 功能：上传、列表、详情、编辑、导入知识库
 */

Vue.component('text-prd-manager', {
    props: {
        initialView: {
            type: String,
            default: 'list' // 默认显示列表
        }
    },
    template: `
    <div class="text-prd-manager">
        <!-- 列表视图 -->
        <div v-if="currentView === 'list'" class="prd-list-view">
            <el-card class="box-card">
                <!-- 标题栏 -->
                <div slot="header" class="clearfix">
                    <span class="section-title">📄 文本PRD管理</span>
                    <el-button 
                        type="primary" 
                        size="small" 
                        style="float: right;"
                        @click="showUploadDialog = true">
                        <i class="el-icon-upload"></i> 上传文本文档
                    </el-button>
                </div>
                
                <!-- 过滤器 -->
                <div class="filter-bar">
                    <el-radio-group v-model="statusFilter" size="small" @change="loadPRDList">
                        <el-radio-button label="">全部</el-radio-button>
                        <el-radio-button label="draft">草稿</el-radio-button>
                        <el-radio-button label="processing">处理中</el-radio-button>
                        <el-radio-button label="completed">已完成</el-radio-button>
                    </el-radio-group>
                </div>
                
                <!-- PRD列表 -->
                <el-table 
                    :data="prdList" 
                    style="width: 100%; margin-top: 20px;"
                    v-loading="loading">
                    <el-table-column prop="name" label="PRD名称" min-width="200">
                        <template slot-scope="scope">
                            <i class="el-icon-document"></i>
                            {{ scope.row.name }}
                        </template>
                    </el-table-column>
                    <el-table-column prop="status" label="状态" width="120">
                        <template slot-scope="scope">
                            <el-tag :type="getStatusType(scope.row)" size="small">
                                {{ getStatusText(scope.row) }}
                            </el-tag>
                        </template>
                    </el-table-column>
                    <el-table-column prop="created_at" label="创建时间" width="180">
                        <template slot-scope="scope">
                            {{ formatDateTime(scope.row.created_at) }}
                        </template>
                    </el-table-column>
                    <el-table-column label="操作" width="280">
                        <template slot-scope="scope">
                            <div style="display: flex; gap: 5px; flex-wrap: wrap; align-items: center;">
                                <el-button 
                                    type="info" 
                                    size="mini" 
                                    @click="viewPRDDetail(scope.row.id)">
                                    查看详情
                                </el-button>
                                <el-button 
                                    type="success" 
                                    size="mini" 
                                    @click="importPRDToKb(scope.row.id)">
                                    导入知识库
                                </el-button>
                                <el-button 
                                    type="danger" 
                                    size="mini" 
                                    v-if="scope.row.status === 'draft'"
                                    @click="deletePRD(scope.row.id)">
                                    删除
                                </el-button>
                            </div>
                        </template>
                    </el-table-column>
                </el-table>
                
                <!-- 分页 -->
                <el-pagination
                    v-if="total > pageSize"
                    @current-change="handlePageChange"
                    :current-page="currentPage"
                    :page-size="pageSize"
                    layout="total, prev, pager, next"
                    :total="total"
                    style="margin-top: 20px; text-align: right;">
                </el-pagination>
            </el-card>
        </div>
        
        <!-- 详情视图 -->
        <div v-else-if="currentView === 'detail'" class="prd-detail-view">
            <el-card class="box-card">
                <div slot="header" class="clearfix">
                    <el-button 
                        type="text" 
                        size="small" 
                        @click="backToList">
                        <i class="el-icon-arrow-left"></i> 返回列表
                    </el-button>
                    <span class="section-title" style="margin-left: 10px;">
                        📄 PRD详情
                    </span>
                </div>
                
                <div v-if="currentPRD" class="prd-detail-content">
                    <!-- 基本信息 -->
                    <div style="background: #fff; border: 1px solid #EBEEF5; border-radius: 4px; overflow: hidden; margin-bottom: 20px;">
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr style="background: #F5F7FA;">
                                <td style="padding: 12px 15px; width: 120px; color: #606266; font-size: 14px; border-bottom: 1px solid #EBEEF5; font-weight: 500;">
                                    PRD名称
                                </td>
                                <td style="padding: 12px 15px; color: #303133; font-size: 14px; border-bottom: 1px solid #EBEEF5; border-left: 1px solid #EBEEF5;">
                                    {{ currentPRD.name }}
                                </td>
                                <td style="padding: 12px 15px; width: 100px; color: #606266; font-size: 14px; border-bottom: 1px solid #EBEEF5; border-left: 1px solid #EBEEF5; font-weight: 500;">
                                    状态
                                </td>
                                <td style="padding: 12px 15px; width: 120px; color: #303133; font-size: 14px; border-bottom: 1px solid #EBEEF5; border-left: 1px solid #EBEEF5;">
                                    <el-tag :type="getStatusType(currentPRD)" size="small">
                                        {{ getStatusText(currentPRD) }}
                                    </el-tag>
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 12px 15px; width: 120px; color: #606266; font-size: 14px; background: #F5F7FA; font-weight: 500;">
                                    创建时间
                                </td>
                                <td style="padding: 12px 15px; color: #303133; font-size: 14px; border-left: 1px solid #EBEEF5;">
                                    {{ formatDateTime(currentPRD.created_at) }}
                                </td>
                                <td style="padding: 12px 15px; width: 100px; color: #606266; font-size: 14px; background: #F5F7FA; border-left: 1px solid #EBEEF5; font-weight: 500;">
                                    更新时间
                                </td>
                                <td style="padding: 12px 15px; width: 120px; color: #303133; font-size: 14px; border-left: 1px solid #EBEEF5;">
                                    {{ formatDateTime(currentPRD.updated_at) }}
                                </td>
                            </tr>
                        </table>
                    </div>
                    
                    <!-- 知识库导入配置 -->
                    <div class="config-section" v-if="currentPRD.status === 'draft'">
                        <h3>知识库导入说明</h3>
                        <div style="padding: 12px 16px; background: #F5F7FA; border-left: 3px solid #409EFF; border-radius: 4px; line-height: 1.7; color: #606266; font-size: 13px;">
                            <div style="margin-bottom: 6px;">
                                文本 PRD 会先做窄清理，只移除模型包裹、确认块等非 PRD 内容，不改写业务事实。
                            </div>
                            <div style="margin-bottom: 6px;">
                                清洗阶段会生成结构化知识单元：content 保留业务对象、动作和关键结果，rules 逐条保留按钮名、字段名、toast、数值、状态、示例、否定规则、页面动作和布局细节。
                            </div>
                            <div>
                                完成后会生成常见问法并写入知识库，供后续问答测试和 API 调用。
                            </div>
                        </div>
                    </div>
                    
                    <!-- PRD内容 -->
                    <div class="content-section">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                            <h3 style="margin: 0;">📝 PRD内容</h3>
                            <div v-if="!editingContent">
                                <el-button 
                                    type="primary" 
                                    size="small"
                                    @click="startEditContent">
                                    <i class="el-icon-edit"></i> 编辑内容
                                </el-button>
                            </div>
                        </div>
                        <div v-if="!editingContent" class="content-display">
                            <div class="markdown-content" v-html="renderedContent"></div>
                        </div>
                        <div v-else class="content-edit">
                            <el-alert
                                v-if="currentPRD.status !== 'draft'"
                                type="warning"
                                :closable="false"
                                style="margin-bottom: 10px;">
                                <span slot="title">
                                    提醒：此PRD状态为「{{ getStatusText(currentPRD) }}」，编辑内容可能会影响后续知识库导入结果。
                                </span>
                            </el-alert>
                            <el-input 
                                type="textarea" 
                                v-model="editContentForm.content"
                                :rows="20"
                                placeholder="请输入Markdown格式的PRD内容">
                            </el-input>
                            <div style="margin-top: 10px;">
                                <el-button type="primary" @click="saveContent">
                                    <i class="el-icon-check"></i> 保存
                                </el-button>
                                <el-button @click="cancelEditContent">
                                    取消
                                </el-button>
                            </div>
                        </div>
                    </div>
                    
                    <!-- 操作按钮 -->
                    <div class="action-bar">
                        <el-button 
                            type="success" 
                            size="large"
                            @click="importCurrentPRDToKb">
                            <i class="el-icon-upload2"></i> 导入知识库
                        </el-button>
                        <el-button 
                            type="danger" 
                            size="large"
                            v-if="currentPRD.status === 'draft'"
                            @click="deleteCurrentPRD">
                            <i class="el-icon-delete"></i> 删除PRD
                        </el-button>
                    </div>
                </div>
            </el-card>
        </div>
        
        <!-- 上传对话框 -->
        <el-dialog 
            title="上传文本文档" 
            :visible.sync="showUploadDialog"
            width="600px"
            :append-to-body="true">
            <el-form :model="uploadForm" label-width="100px">
                <el-form-item label="文档名称">
                    <el-input 
                        v-model="uploadForm.name" 
                        placeholder="请输入文档名称">
                    </el-input>
                </el-form-item>
                <el-form-item label="选择文件">
                    <input 
                        type="file" 
                        accept=".txt,.md,.markdown,.text,.log"
                        @change="handleFileSelect"
                        ref="fileInput">
                </el-form-item>
                <el-form-item label="或粘贴内容">
                    <el-input 
                        type="textarea" 
                        v-model="uploadForm.content"
                        :rows="10"
                        placeholder="请粘贴PRD文档内容（支持纯文本/Markdown等格式）">
                    </el-input>
                </el-form-item>
            </el-form>
            <span slot="footer" class="dialog-footer">
                <el-button @click="showUploadDialog = false">取消</el-button>
                <el-button type="primary" @click="uploadPRD" :loading="uploading">
                    <i class="el-icon-upload"></i> 上传
                </el-button>
            </span>
        </el-dialog>
    </div>
    `,
    
    data() {
        return {
            // 视图控制
            currentView: 'list',  // list/detail
            
            // 列表数据
            prdList: [],
            statusFilter: '',
            total: 0,
            currentPage: 1,
            pageSize: 20,
            loading: false,
            
            // 详情数据
            currentPRD: null,
            editingContent: false,
            editContentForm: {
                content: ''
            },
            
            // 上传对话框
            showUploadDialog: false,
            uploadForm: {
                name: '',
                content: ''
            },
            uploading: false
        };
    },
    
    computed: {
        renderedContent() {
            if (!this.currentPRD || !this.currentPRD.content) {
                return '';
            }
            return safeRenderMarkdown(this.currentPRD.content);
        }
    },
    
    mounted() {
        // 根据传入的 initialView 设置初始视图
        if (this.initialView) {
            this.currentView = this.initialView === 'create' ? 'list' : this.initialView;
            // 如果是 create 模式，自动打开上传对话框
            if (this.initialView === 'create') {
                this.$nextTick(() => {
                    this.showUploadDialog = true;
                });
            }
        }
        // 如果是列表视图，加载列表
        if (this.currentView === 'list') {
            this.loadPRDList();
        }
    },
    
    methods: {
        // ========== 列表操作 ==========
        
        async loadPRDList() {
            this.loading = true;
            try {
                const params = {
                    status: this.statusFilter,
                    limit: this.pageSize,
                    offset: (this.currentPage - 1) * this.pageSize
                };
                
                const response = await axios.get(`${apiBaseUrl}/prds`, { params });
                
                if (response.data.success) {
                    this.prdList = response.data.data.prds;
                    this.total = response.data.data.total;
                } else {
                    this.$message.error('加载PRD列表失败: ' + response.data.message);
                }
            } catch (error) {
                console.error('加载PRD列表异常:', error);
                this.$message.error('加载PRD列表失败');
            } finally {
                this.loading = false;
            }
        },
        
        handlePageChange(page) {
            this.currentPage = page;
            this.loadPRDList();
        },
        
        // ========== 上传 ==========
        
        handleFileSelect(event) {
            const file = event.target.files[0];
            if (!file) return;
            
            // 自动填充文件名
            if (!this.uploadForm.name) {
                this.uploadForm.name = file.name;
            }
            
            // 读取文件内容
            const reader = new FileReader();
            reader.onload = (e) => {
                this.uploadForm.content = e.target.result;
            };
            reader.readAsText(file);
        },
        
        async uploadPRD() {
            if (!this.uploadForm.content) {
                this.$message.warning('请选择文件或粘贴内容');
                return;
            }
            
            if (!this.uploadForm.name) {
                this.uploadForm.name = `PRD_${new Date().getTime()}.md`;
            }
            
            this.uploading = true;
            try {
                const response = await axios.post(`${apiBaseUrl}/prds/upload`, {
                    name: this.uploadForm.name,
                    content: this.uploadForm.content
                });
                
                if (response.data.success) {
                    this.$message.success('上传成功');
                    this.showUploadDialog = false;
                    
                    // 重置表单
                    this.uploadForm = { name: '', content: '' };
                    this.$refs.fileInput.value = '';
                    
                    // 刷新列表并跳转到详情
                    await this.loadPRDList();
                    this.viewPRDDetail(response.data.data.prd_id);
                } else {
                    this.$message.error('上传失败: ' + response.data.message);
                }
            } catch (error) {
                console.error('上传PRD异常:', error);
                this.$message.error('上传失败');
            } finally {
                this.uploading = false;
            }
        },
        
        // ========== 详情操作 ==========
        
        async viewPRDDetail(prd_id) {
            this.loading = true;
            try {
                const response = await axios.get(`${apiBaseUrl}/prds/${prd_id}`);
                
                if (response.data.success) {
                    this.currentPRD = response.data.data.prd;
                    
                    // 切换到详情视图
                    this.currentView = 'detail';
                } else {
                    this.$message.error('加载PRD详情失败: ' + response.data.message);
                }
            } catch (error) {
                console.error('加载PRD详情异常:', error);
                this.$message.error('加载PRD详情失败');
            } finally {
                this.loading = false;
            }
        },
        
        backToList() {
            // 通知父组件刷新知识库统计和文档列表。
            this.$emit('back-to-parent');
            
            // 组件内部视图切换（用于组件独立使用时）
            this.currentView = 'list';
            this.currentPRD = null;
            this.editingContent = false;
            this.loadPRDList();
        },
        
        // ========== 内容编辑 ==========
        
        startEditContent() {
            this.editContentForm.content = this.currentPRD.content;
            this.editingContent = true;
        },
        
        cancelEditContent() {
            this.editingContent = false;
        },
        
        async saveContent() {
            try {
                // 如果不是草稿状态，显示二次确认
                if (this.currentPRD.status !== 'draft') {
                    const confirmResult = await this.$confirm(
                        '此PRD已导入或处理过，修改内容可能会影响后续知识库导入结果。确认保存？',
                        '确认保存',
                        {
                            confirmButtonText: '确认保存',
                            cancelButtonText: '取消',
                            type: 'warning'
                        }
                    ).catch(() => false);
                    
                    if (!confirmResult) return;
                }
                
                const response = await axios.put(
                    `${apiBaseUrl}/prds/${this.currentPRD.id}`,
                    { content: this.editContentForm.content }
                );
                
                if (response.data.success) {
                    this.$message.success('内容保存成功');
                    this.currentPRD.content = this.editContentForm.content;
                    this.editingContent = false;
                } else {
                    this.$message.error('保存内容失败: ' + response.data.message);
                }
            } catch (error) {
                if (error !== false) {  // 不是用户取消
                    console.error('保存内容异常:', error);
                    this.$message.error('保存内容失败');
                }
            }
        },
        
        // ========== 导入知识库 ==========
        
        async importCurrentPRDToKb() {
            this.importPRDToKb(this.currentPRD.id);
        },
        
        async importPRDToKb(prd_id) {
            try {
                // 先获取最新的PRD数据，确保导入使用最新内容
                const prdResponse = await axios.get(`${apiBaseUrl}/prds/${prd_id}`);
                if (!prdResponse.data.success) {
                    this.$message.error('无法获取PRD信息');
                    return;
                }
                
                const prd = (prdResponse.data.data && prdResponse.data.data.prd) || prdResponse.data.prd;
                if (!prd) {
                    this.$message.error('无法获取PRD信息');
                    return;
                }
                
                // 确认对话框
                const confirmResult = await this.$confirm(
                    `将把该文本 PRD 清洗并导入知识库，确认继续？`,
                    '确认导入知识库',
                    {
                        confirmButtonText: '确认导入',
                        cancelButtonText: '取消',
                        type: 'info'
                    }
                ).catch(() => false);
                
                if (!confirmResult) return;
                
                // 导入知识库
                const response = await axios.post(`${apiBaseUrl}/kb/v1/documents/import-text-prd`, {
                    title: prd.name,
                    product: prd.business || '',
                    module: prd.name,
                    version: prd.version || '',
                    change_type: '',
                    content: prd.content || '',
                    rebuild: true
                });
                
                if (response.data.success) {
                    this.$message.success('已导入知识库');
                    await this.loadPRDList();
                } else {
                    this.$message.error('导入知识库失败: ' + (response.data.error || response.data.message || '未知错误'));
                }
            } catch (error) {
                if (error !== false) {  // 不是用户取消
                    console.error('导入知识库异常:', error);
                    this.$message.error('导入知识库失败');
                }
            }
        },
        
        // ========== 删除 ==========
        
        async deleteCurrentPRD() {
            this.deletePRD(this.currentPRD.id, true);
        },
        
        async deletePRD(prd_id, isFromDetail = false) {
            try {
                const confirmResult = await this.$confirm(
                    '确认删除该PRD？删除后无法恢复。',
                    '确认删除',
                    {
                        confirmButtonText: '确认删除',
                        cancelButtonText: '取消',
                        type: 'warning'
                    }
                ).catch(() => false);
                
                if (!confirmResult) return;
                
                const response = await axios.delete(`${apiBaseUrl}/prds/${prd_id}`);
                
                if (response.data.success) {
                    this.$message.success('删除成功');
                    
                    if (isFromDetail) {
                        // 从详情页删除，返回列表
                        this.backToList();
                    } else {
                        // 从列表删除，刷新列表
                        this.loadPRDList();
                    }
                } else {
                    this.$message.error('删除失败: ' + response.data.message);
                }
            } catch (error) {
                if (error !== false) {
                    console.error('删除PRD异常:', error);
                    this.$message.error('删除失败');
                }
            }
        },
        
        // ========== 工具方法 ==========
        
        getStatusType(statusOrPrd) {
            // 兼容传入status字符串或prd对象
            const status = typeof statusOrPrd === 'string' 
                ? statusOrPrd 
                : statusOrPrd.status;
            
            const typeMap = {
                'draft': 'info',
                'processing': 'warning',
                'completed': 'success',
                'failed': 'danger'
            };
            return typeMap[status] || 'info';
        },
        
        getStatusText(statusOrPrd) {
            // 兼容传入status字符串或prd对象
            const status = typeof statusOrPrd === 'string' 
                ? statusOrPrd 
                : statusOrPrd.status;
            
            const textMap = {
                'draft': '草稿',
                'processing': '处理中',
                'completed': '已完成',
                'failed': '失败'
            };
            return textMap[status] || status;
        },
        
        formatDateTime(dateTimeStr) {
            if (!dateTimeStr) return '-';
            try {
                const date = new Date(dateTimeStr);
                return date.toLocaleString('zh-CN', {
                    year: 'numeric',
                    month: '2-digit',
                    day: '2-digit',
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit'
                });
            } catch (e) {
                return dateTimeStr;
            }
        }
    }
});

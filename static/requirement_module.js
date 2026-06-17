/**
 * 需求模块组件 - 阶段1实现
 * 功能：图片上传、备注填写、需求模块管理
 */

Vue.component('requirement-module-component', {
    props: {
        initialView: {
            type: String,
            default: 'list' // 默认显示列表
        }
    },
    template: `
        <div class="requirement-module-component">
            <!-- ========== 视图切换：列表/新建/详情 ========== -->
            
            <!-- 列表视图 -->
            <div v-if="currentView === 'list'" class="module-list-view">
                <el-card class="box-card">
                    <div slot="header" class="clearfix">
                        <span class="card-title">📋 我的需求模块</span>
                        <el-button 
                            style="float: right" 
                            type="primary"
                            icon="el-icon-plus"
                            @click="showCreateView"
                        >
                            新建需求模块
                        </el-button>
                    </div>
                    
                    <!-- 模块列表 -->
                    <el-table
                        :data="modules"
                        style="width: 100%"
                        v-loading="loading"
                        @row-click="handleRowClick"
                    >
                        <el-table-column prop="name" label="需求模块名称" min-width="250">
                            <template slot-scope="scope">
                                <div class="module-name-cell">
                                    <i class="el-icon-folder-opened"></i>
                                    <span>{{ scope.row.name }}</span>
                                </div>
                            </template>
                        </el-table-column>
                        
                        <el-table-column prop="image_count" label="图片" width="100">
                            <template slot-scope="scope">
                                <el-tag size="mini" type="info">
                                    {{ scope.row.image_count }}张
                                </el-tag>
                            </template>
                        </el-table-column>
                        
                        <el-table-column prop="notes" label="备注" width="100">
                            <template slot-scope="scope">
                                <el-tag size="mini" v-if="hasNotes(scope.row)" type="success">
                                    已填写
                                </el-tag>
                                <span v-else style="color: #909399;">-</span>
                            </template>
                        </el-table-column>
                        
                        <el-table-column prop="status" label="状态" width="100">
                            <template slot-scope="scope">
                                <el-tag :type="getStatusType(scope.row.status)" size="mini">
                                    {{ getStatusText(scope.row.status) }}
                                </el-tag>
                            </template>
                        </el-table-column>
                        
                        <el-table-column prop="created_at" label="创建时间" width="180">
                            <template slot-scope="scope">
                                {{ formatDateTime(scope.row.created_at) }}
                            </template>
                        </el-table-column>
                        
                        <el-table-column label="操作" width="320" fixed="right">
                            <template slot-scope="scope">
                                <div style="display: flex; gap: 5px; align-items: center;">
                                    <el-button 
                                        size="mini" 
                                        type="info"
                                        icon="el-icon-view"
                                        @click.stop="viewModule(scope.row)"
                                    >
                                        查看
                                    </el-button>
                                    <el-button 
                                        v-if="scope.row.status === 'draft'"
                                        size="mini" 
                                        type="primary"
                                        icon="el-icon-edit"
                                        @click.stop="editModule(scope.row)"
                                    >
                                        编辑
                                    </el-button>
                                    <el-button 
                                        v-if="scope.row.status !== 'processing'"
                                        size="mini" 
                                        type="success"
                                        icon="el-icon-upload2"
                                        @click.stop="viewModule(scope.row)"
                                    >
                                        导入知识库
                                    </el-button>
                                    <el-button 
                                        v-if="scope.row.status === 'draft'"
                                        size="mini" 
                                        type="danger"
                                        icon="el-icon-delete"
                                        @click.stop="deleteModuleConfirm(scope.row)"
                                    >
                                        删除
                                    </el-button>
                                    <el-button 
                                        v-if="scope.row.status === 'failed'"
                                        size="mini" 
                                        type="warning"
                                        icon="el-icon-refresh"
                                        @click.stop="retryModule(scope.row)"
                                    >
                                        重试
                                    </el-button>
                                </div>
                            </template>
                        </el-table-column>
                    </el-table>
                    
                    <!-- 分页 -->
                    <el-pagination
                        v-if="total > 0"
                        @current-change="handlePageChange"
                        :current-page="currentPage"
                        :page-size="pageSize"
                        layout="total, prev, pager, next"
                        :total="total"
                        style="margin-top: 20px; text-align: right;"
                    >
                    </el-pagination>
                </el-card>
            </div>
            
            <!-- 新建/编辑视图 -->
            <div v-else-if="currentView === 'create'" class="module-create-view single-page">
                <el-card class="box-card">
                    <div slot="header" class="clearfix">
                        <el-button 
                            icon="el-icon-arrow-left" 
                            @click="backToList"
                            size="small"
                        >
                            返回列表
                        </el-button>
                        <span class="card-title" style="margin-left: 20px;">
                            {{ editingModule ? '编辑需求模块' : '新建需求模块' }}
                        </span>
                    </div>
                    
                    <!-- 使用前必读 - 简洁横幅 -->
                    <div style="background: linear-gradient(135deg, #FEF0F0 0%, #FFE6E6 100%); padding: 16px 24px; border-radius: 8px; margin-bottom: 20px; border-left: 5px solid #F56C6C; box-shadow: 0 2px 12px rgba(245, 108, 108, 0.15); display: flex; align-items: center; justify-content: space-between;">
                        <div style="display: flex; align-items: center; gap: 15px;">
                            <div style="font-size: 32px; animation: pulse 2s infinite;">⚠️</div>
                            <div>
                                <div style="color: #F56C6C; font-size: 18px; font-weight: bold; margin-bottom: 3px;">
                                    ⭐ 使用前必读 - 图片需求上传规范
                                </div>
                                <div style="color: #909399; font-size: 13px;">
                                    首次使用？点击右侧按钮查看详细的<strong>模块拆分、命名规范</strong>等重要信息 →
                                </div>
                            </div>
                        </div>
                        <el-button 
                            type="danger" 
                            icon="el-icon-reading" 
                            size="medium"
                            @click="showGuideDrawer = true"
                            style="font-weight: bold;">
                            查看完整使用指南
                        </el-button>
                    </div>
                    
                    <!-- 使用指南抽屉 -->
                    <el-drawer
                        title="📘 图片需求上传完整指南"
                        :visible.sync="showGuideDrawer"
                        direction="rtl"
                        size="65%"
                        :append-to-body="true"
                        :modal="true"
                        :wrapperClosable="true">
                        
                        <div style="padding: 20px; background: #f5f7fa; min-height: 100%; overflow-y: auto;">
                            <!-- 两个卡片，在抽屉中垂直排列 -->
                    <div style="display: flex; flex-direction: column; gap: 20px; font-size: 13px; color: #606266; background: transparent;">
                        
                        <!-- 卡片1：模块拆分规则 -->
                        <div style="background: #fff; border: 2px solid #E8E8E8; border-radius: 8px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">
                            <div style="margin-bottom: 15px; padding-bottom: 12px; border-bottom: 2px solid #f5576c;">
                                <div style="font-size: 24px; margin-bottom: 6px;">📦</div>
                                <strong style="color: #303133; font-size: 16px; display: block;">大版本需求需要拆分模块</strong>
                            </div>
                            
                            <!-- 拆分判断条件 -->
                            <div style="background: #FFE6E6; padding: 12px 14px; border-radius: 6px; margin-bottom: 14px; border: 2px solid #F56C6C;">
                                <div style="font-weight: bold; font-size: 13px; margin-bottom: 8px; color: #F56C6C; text-align: center;">⚠️ 大需求拆分判断条件</div>
                                <div style="background: #fff; padding: 10px 12px; border-radius: 4px; font-size: 13px; line-height: 1.8; color: #303133;">
                                    当需求<strong style="color: #F56C6C; font-size: 14px;">超过4张</strong>墨刀/UE图时，<strong style="color: #F56C6C;">必须拆分为多个模块</strong>，逐个生成 PRD 并导入知识库
                                </div>
                            </div>
                            
                            <div style="background: #FFF5F7; padding: 12px 14px; border-radius: 6px; margin-bottom: 14px; border-left: 3px solid #F56C6C;">
                                <div style="font-weight: bold; font-size: 13px; margin-bottom: 6px; color: #F56C6C;">1️⃣ 较大的子功能模块</div>
                                <div style="color: #606266; font-size: 12px; line-height: 1.7; padding-left: 10px;">
                                    <div style="margin-bottom: 4px;">• 涉及几个页面的完整功能</div>
                                    <div style="margin-bottom: 4px;">• 建议放在一起，单个模块<strong style="color: #F56C6C;">不超过4张图</strong></div>
                                    <div style="margin-bottom: 4px;">• 模块名称：<code style="background: #FFF3CD; padding: 2px 6px; font-size: 11px; border-radius: 3px;">项目v版本_功能名称</code></div>
                                    <div>• 示例：<code style="background: #F5F5F5; padding: 2px 6px; font-size: 11px; border-radius: 3px;">业务系统v1.2.0_新增批量导入</code></div>
                                </div>
                            </div>
                            
                            <div style="background: #FFF5F7; padding: 12px 14px; border-radius: 6px; margin-bottom: 14px; border-left: 3px solid #F56C6C;">
                                <div style="font-weight: bold; font-size: 13px; margin-bottom: 6px; color: #F56C6C;">2️⃣ 多个小改动点</div>
                                <div style="color: #606266; font-size: 12px; line-height: 1.7; padding-left: 10px;">
                                    <div style="margin-bottom: 4px;">• 零散的小优化</div>
                                    <div style="margin-bottom: 4px;">• 可以放在一起，总计<strong style="color: #F56C6C;">不超过4张图</strong></div>
                                    <div style="margin-bottom: 4px;">• 模块名称：<code style="background: #FFF3CD; padding: 2px 6px; font-size: 11px; border-radius: 3px;">项目v版本_多处改动</code> 或 <code style="background: #FFF3CD; padding: 2px 6px; font-size: 11px; border-radius: 3px;">项目v版本_多处优化</code></div>
                                    <div>• 示例：<code style="background: #F5F5F5; padding: 2px 6px; font-size: 11px; border-radius: 3px;">业务系统v1.2.0_多处优化</code></div>
                                </div>
                            </div>
                            
                            <div style="background: #FFF3E0; padding: 12px 14px; border-radius: 4px; border-left: 3px solid #E6A23C;">
                                <div style="color: #F56C6C; font-weight: bold; font-size: 13px; line-height: 1.6;">
                                    💡 核心原则：单个模块<strong>最多4张图</strong>，超过请拆分为多个模块分别创建
                                </div>
                            </div>
                        </div>
                        
                        <!-- 卡片2：文件命名规范 -->
                        <div style="background: #fff; border: 2px solid #E8E8E8; border-radius: 8px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">
                            <div style="margin-bottom: 15px; padding-bottom: 12px; border-bottom: 2px solid #00f2fe;">
                                <div style="font-size: 24px; margin-bottom: 6px;">🏷️</div>
                                <strong style="color: #303133; font-size: 16px; display: block;">图片文件名必须标记类型</strong>
                            </div>
                            
                            <div style="background: #F0FBFF; padding: 12px 14px; border-radius: 4px; margin-bottom: 14px; border-left: 3px solid #409EFF;">
                                <div style="color: #606266; font-size: 13px; line-height: 1.6;">
                                    每张图片文件名必须以<strong style="color: #F56C6C;">[变更类型]</strong>开头，便于AI理解需求性质
                                </div>
                            </div>
                            
                            <div style="margin-bottom: 14px;">
                                <div style="font-weight: bold; font-size: 13px; margin-bottom: 10px; color: #303133;">变更类型：</div>
                                <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                                    <div style="background: #F0F9FF; padding: 8px 12px; border-radius: 4px; border: 1px solid #D1E7F8;">
                                        <strong style="color: #67C23A; font-size: 12px;">[新增]</strong> <span style="font-size: 11px; color: #909399;">新功能、新页面</span>
                                    </div>
                                    <div style="background: #FFF9E6; padding: 8px 12px; border-radius: 4px; border: 1px solid #FFE7B0;">
                                        <strong style="color: #E6A23C; font-size: 12px;">[修改]</strong> <span style="font-size: 11px; color: #909399;">功能调整、界面改版</span>
                                    </div>
                                    <div style="background: #FEF0F0; padding: 8px 12px; border-radius: 4px; border: 1px solid #FFD4D4;">
                                        <strong style="color: #F56C6C; font-size: 12px;">[删除]</strong> <span style="font-size: 11px; color: #909399;">移除功能</span>
                                    </div>
                                    <div style="background: #F0F9FF; padding: 8px 12px; border-radius: 4px; border: 1px solid #D1E7F8;">
                                        <strong style="color: #409EFF; font-size: 12px;">[优化]</strong> <span style="font-size: 11px; color: #909399;">性能、体验优化</span>
                                    </div>
                                </div>
                            </div>
                            
                            <div style="background: #F5F5F5; padding: 12px 14px; border-radius: 4px; font-size: 12px; line-height: 1.7;">
                                <div style="margin-bottom: 8px;">
                                    <strong style="color: #303133;">标准格式：</strong><br>
                                    <code style="background: #FFF3CD; padding: 3px 7px; border-radius: 3px; color: #856404; font-size: 11px;">[变更类型]_序号_[功能描述].扩展名</code>
                                </div>
                                <div style="margin-bottom: 8px;">
                                    <strong style="color: #303133;">示例：</strong><br>
                                    <code style="background: #fff; padding: 3px 6px; border-radius: 3px; border: 1px solid #E8E8E8; margin-right: 5px; font-size: 11px;">[新增]_01_会议通知界面.png</code><br>
                                    <code style="background: #fff; padding: 3px 6px; border-radius: 3px; border: 1px solid #E8E8E8; margin-top: 5px; display: inline-block; font-size: 11px;">[修改]_02_地图交互逻辑.png</code>
                                </div>
                                <div style="color: #909399; font-size: 11px; margin-top: 8px;">
                                    变更类型：<strong>[新增]</strong> <strong>[修改]</strong> <strong>[删除]</strong> <strong>[优化]</strong><br>
                                    序号规则：01、02、03... （按优先级排序）
                                </div>
                            </div>
                        </div>
                        
                    </div>
                        </div>
                    </el-drawer>
                    
                    <el-form :model="moduleForm" label-width="150px">
                        <!-- 第一部分：基本信息 -->
                        <div class="form-section">
                            <h3 class="section-title">📋 基本信息</h3>
                            
                            <el-form-item label="需求大模块名称" required>
                                <div style="display: flex; gap: 20px; align-items: flex-start;">
                                    <el-input 
                                        v-model="moduleForm.name" 
                                        placeholder="如：业务系统v1.2.0_新增批量导入"
                                        style="width: 600px;"
                                    ></el-input>
                                    <div style="flex: 1; padding: 12px; background: #FFF9E6; border-left: 3px solid #E6A23C; border-radius: 4px;">
                                        <div style="color: #606266; font-size: 13px; line-height: 1.6;">
                                            📝 <strong style="color: #E6A23C;">格式：</strong><strong>项目v版本_功能名称</strong> 或 <strong>项目v版本_多处改动</strong>
                                        </div>
                                    </div>
                                </div>
                            </el-form-item>
                        </div>
                        
                        <!-- 第二部分：上传图片 -->
                        <div class="form-section">
                            <h3 class="section-title">📸 上传图片 <span class="required">*</span></h3>
                            
                            <el-form-item>
                                <div style="display: flex; gap: 20px; align-items: flex-start;">
                                    <!-- 左侧：上传区域 -->
                                    <div style="flex: 0 0 400px;">
                                        <el-upload
                                            class="upload-demo"
                                            drag
                                            :auto-upload="false"
                                            :on-change="handleFileChange"
                                            :on-remove="handleFileRemove"
                                            :file-list="fileList"
                                            multiple
                                            accept="image/*"
                                            list-type="picture"
                                        >
                                            <i class="el-icon-upload"></i>
                                            <div class="el-upload__text">
                                                将图片拖到此处，或<em>点击上传</em>
                                            </div>
                                            <div class="el-upload__tip" slot="tip">
                                                支持PNG、JPG格式，单张不超过5MB
                                            </div>
                                        </el-upload>
                                    </div>
                                    
                                    <!-- 右侧：命名规范与备注说明 -->
                                    <div style="flex: 1;">
                                        <el-alert
                                            type="warning"
                                            :closable="false"
                                            style="margin-bottom: 12px;"
                                        >
                                            <template slot="title">
                                                <div style="font-size: 13px; line-height: 1.8;">
                                                    <strong>📋 文件命名规范（必读）</strong>
                                                </div>
                                            </template>
                                            <div style="font-size: 12px; line-height: 1.8; color: #606266;">
                                                <strong style="color: #E6A23C;">标准格式：</strong>
                                                <code style="background: #fff3cd; padding: 2px 6px; border-radius: 3px; color: #856404;">[变更类型]_序号_[功能描述].扩展名</code>
                                                <div style="margin-top: 6px;">
                                                    <strong style="color: #E6A23C;">示例：</strong><br>
                                                    <code style="background: #f5f5f5; padding: 2px 5px; margin-right: 4px;">[新增]_01_会议通知界面.png</code><br>
                                                    <code style="background: #f5f5f5; padding: 2px 5px; margin-top: 4px; display: inline-block;">[修改]_02_地图交互逻辑.png</code>
                                                </div>
                                                <div style="margin-top: 6px; color: #909399; font-size: 11px;">
                                                    变更类型：<strong>[新增]</strong> <strong>[修改]</strong> <strong>[删除]</strong> <strong>[优化]</strong><br>
                                                    序号规则：01、02、03... （按优先级排序）
                                                </div>
                                            </div>
                                        </el-alert>
                                        
                                        <el-alert
                                            type="info"
                                            :closable="false"
                                        >
                                            <template slot="title">
                                                <div style="font-size: 13px; line-height: 1.8;">
                                                    <strong>💡 图片备注机制（可选）</strong>
                                                </div>
                                            </template>
                                            <div style="font-size: 12px; line-height: 1.8; color: #606266;">
                                                <div style="margin-bottom: 6px;">
                                                    如需对图片添加特殊说明，可在文件名后加 
                                                    <code style="background: #e1f3f8; padding: 2px 6px; border-radius: 3px; color: #0d6efd; font-weight: 500;">#备注内容</code>
                                                </div>
                                                <div style="margin-bottom: 6px;">
                                                    <strong style="color: #409EFF;">示例：</strong><br>
                                                    <code style="background: #f5f5f5; padding: 2px 5px; font-size: 11px; display: inline-block; max-width: 100%; word-break: break-all;">
                                                        [新增]_01_会议界面<span style="color: #409EFF; font-weight: bold;">#图片缺少交互流程说明</span>.png
                                                    </code>
                                                </div>
                                                <div style="color: #909399; font-size: 11px;">
                                                    <strong>适用场景：</strong>图片信息缺失、图片有明显错误、AI可能理解有误的地方<br>
                                                    <strong>可选性：</strong>图片信息完整且无需澄清时无需添加备注
                                                </div>
                                            </div>
                                        </el-alert>
                                    </div>
                                </div>
                                
                                <!-- 已上传图片展示 -->
                                <div v-if="uploadedImages.length > 0" class="uploaded-images-section">
                                    <h4>已上传 {{ uploadedImages.length }} 张图片</h4>
                                    
                                    <div class="image-gallery">
                                        <div 
                                            v-for="(img, index) in uploadedImages" 
                                            :key="img.id"
                                            class="image-item"
                                        >
                                            <!-- 图片预览 -->
                                            <div class="image-thumbnail" @click="previewImage(img)">
                                                <img :src="getImagePreviewUrl(img)" :alt="img.name">
                                                <div class="image-overlay">
                                                    <i class="el-icon-zoom-in"></i>
                                                </div>
                                            </div>
                                            
                                            <!-- 图片信息 -->
                                            <div class="image-info">
                                                <div class="image-name" :title="img.original_name || img.name">
                                                    {{ img.order }}. {{ img.original_name || img.name }}
                                                </div>
                                                <div class="image-size">{{ formatFileSize(img.size) }}</div>
                                            </div>
                                            
                                            <!-- 操作按钮 -->
                                            <div class="image-actions">
                                                <el-button 
                                                    size="mini" 
                                                    type="info"
                                                    icon="el-icon-view"
                                                    @click="previewImage(img)"
                                                >查看</el-button>
                                                <el-button 
                                                    size="mini" 
                                                    type="danger" 
                                                    icon="el-icon-delete"
                                                    @click="deleteUploadedImage(img.id)"
                                                >删除</el-button>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </el-form-item>
                        </div>
                        
                        <!-- 第三部分：填写备注 -->
                        <div class="form-section">
                            <h3 class="section-title">📝 备注信息（可选）</h3>
                            
                            <el-alert
                                title="提示：备注内容为可选项，如果图片已经包含所有信息，可以不填写"
                                type="info"
                                :closable="false"
                                show-icon
                                style="margin-bottom: 20px;"
                            ></el-alert>
                            
                            <!-- 需求文档补充 -->
                            <el-form-item label="需求文档补充">
                                <div style="display: flex; gap: 20px; align-items: flex-start;">
                                    <el-input
                                        v-model="notesForm.requirement"
                                        type="textarea"
                                        :rows="5"
                                        placeholder="项目背景、需求目录、功能点说明等（可不填）"
                                        style="width: 600px;"
                                    ></el-input>
                                    <div style="flex: 1; padding: 12px; background: #F0F9FF; border-left: 3px solid #409EFF; border-radius: 4px;">
                                        <div style="color: #606266; font-size: 13px; line-height: 1.6;">
                                            💡 <strong style="color: #409EFF;">说明：</strong>可补充需求背景、涉及到的历史功能等信息，如无需补充可略过
                                        </div>
                                    </div>
                                </div>
                            </el-form-item>
                        </div>
                        
                        <!-- 底部操作按钮 -->
                        <div class="form-footer">
                            <el-button @click="backToList" size="large">取消</el-button>
                            <el-button 
                                type="primary" 
                                @click="saveModule"
                                :loading="saving"
                                size="large"
                            >
                                {{ editingModule ? '保存修改' : '保存草稿' }}
                            </el-button>
                        </div>
                    </el-form>
                </el-card>
            </div>
            
            <!-- 详情视图 -->
            <div v-else-if="currentView === 'detail'" class="module-detail-view">
                <el-card class="box-card">
                    <div slot="header" class="clearfix">
                        <el-button 
                            icon="el-icon-arrow-left" 
                            @click="backToList"
                            size="small"
                        >
                            返回列表
                        </el-button>
                        <span class="card-title" style="margin-left: 20px;">
                            {{ currentModule ? currentModule.name : '需求模块详情' }}
                        </span>
                        <div style="float: right;">
                            <el-button 
                                v-if="currentModule && currentModule.status === 'draft'"
                                size="small" 
                                icon="el-icon-edit"
                                @click="editModule(currentModule)"
                            >
                                编辑
                            </el-button>
                            <el-button 
                                v-if="currentModule && currentModule.status !== 'processing'"
                                size="small" 
                                type="success"
                                icon="el-icon-upload2"
                                @click="confirmImportToKb"
                            >
                                导入知识库
                            </el-button>
                        </div>
                    </div>
                    
                    <div v-if="currentModule">
                        <!-- 基本信息 -->
                        <div style="background: #fff; border: 1px solid #EBEEF5; border-radius: 4px; overflow: hidden; margin-bottom: 20px;">
                            <table style="width: 100%; border-collapse: collapse;">
                                <tr style="background: #F5F7FA;">
                                    <td style="padding: 12px 15px; width: 150px; color: #606266; font-size: 14px; border-bottom: 1px solid #EBEEF5; font-weight: 500;">
                                        需求模块名称
                                    </td>
                                    <td style="padding: 12px 15px; color: #303133; font-size: 14px; border-bottom: 1px solid #EBEEF5; border-left: 1px solid #EBEEF5;">
                                        {{ currentModule.name }}
                                    </td>
                                    <td style="padding: 12px 15px; width: 120px; color: #606266; font-size: 14px; border-bottom: 1px solid #EBEEF5; border-left: 1px solid #EBEEF5; font-weight: 500;">
                                        状态
                                    </td>
                                    <td style="padding: 12px 15px; width: 150px; color: #303133; font-size: 14px; border-bottom: 1px solid #EBEEF5; border-left: 1px solid #EBEEF5;">
                                        <el-tag :type="getStatusType(currentModule.status)" size="small">
                                            {{ getStatusText(currentModule.status) }}
                                        </el-tag>
                                    </td>
                                </tr>
                                <tr>
                                    <td style="padding: 12px 15px; width: 150px; color: #606266; font-size: 14px; background: #F5F7FA; font-weight: 500;">
                                        图片数量
                                    </td>
                                    <td style="padding: 12px 15px; color: #303133; font-size: 14px; border-left: 1px solid #EBEEF5;">
                                        {{ currentModule.image_count }} 张
                                    </td>
                                    <td style="padding: 12px 15px; width: 120px; color: #606266; font-size: 14px; background: #F5F7FA; border-left: 1px solid #EBEEF5; font-weight: 500;">
                                        创建时间
                                    </td>
                                    <td style="padding: 12px 15px; width: 150px; color: #303133; font-size: 14px; border-left: 1px solid #EBEEF5;">
                                        {{ formatDateTime(currentModule.created_at) }}
                                    </td>
                                </tr>
                            </table>
                        </div>
                        
                        <!-- 图片列表 -->
                        <div class="section" v-if="currentModule.images && currentModule.images.length > 0">
                            <h3>📸 上传的图片 ({{ currentModule.images.length }}张)</h3>
                            <div class="image-gallery">
                                <div 
                                    v-for="img in currentModule.images" 
                                    :key="img.id"
                                    class="image-item"
                                >
                                    <div class="image-thumbnail" @click="previewImage(img)">
                                        <img :src="getImagePreviewUrl(img)" :alt="img.name">
                                        <div class="image-overlay">
                                            <i class="el-icon-zoom-in"></i>
                                        </div>
                                    </div>
                                    <div class="image-info">
                                        <div class="image-name">{{ img.order }}. {{ img.original_name || img.name }}</div>
                                        <div class="image-size">{{ formatFileSize(img.size) }}</div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <!-- 备注信息 -->
                        <div class="section">
                            <h3>📝 备注信息</h3>
                            <div style="background: #fff; border: 1px solid #EBEEF5; border-radius: 4px; overflow: hidden;">
                                <table style="width: 100%; border-collapse: collapse;">
                                    <tr>
                                        <td style="padding: 12px 15px; width: 150px; color: #606266; font-size: 14px; background: #F5F7FA; vertical-align: top; border-bottom: 1px solid #EBEEF5; font-weight: 500;">
                                            需求文档补充
                                        </td>
                                        <td style="padding: 12px 15px; color: #303133; font-size: 14px; border-bottom: 1px solid #EBEEF5; border-left: 1px solid #EBEEF5;">
                                            <pre class="notes-content">{{ currentModule.notes_requirement || '暂无' }}</pre>
                                        </td>
                                    </tr>
                                </table>
                            </div>
                        </div>
                    </div>
                </el-card>
            </div>
            
            <!-- 图片预览对话框 -->
            <el-dialog
                :visible.sync="previewDialogVisible"
                width="80%"
                :append-to-body="true"
            >
                <img 
                    v-if="currentPreviewImage" 
                    :src="getImagePreviewUrl(currentPreviewImage)" 
                    style="width: 100%;"
                >
                <div slot="title">
                    {{ currentPreviewImage ? currentPreviewImage.name : '' }}
                </div>
            </el-dialog>
            
            <!-- 图片知识库导入进度对话框 -->
            <el-dialog
                title="导入知识库"
                :visible.sync="pipelineProgressVisible"
                width="600px"
                :close-on-click-modal="false"
                :close-on-press-escape="false"
                :show-close="pipelineProgress.status === 'completed' || pipelineProgress.status === 'failed'"
            >
                <div v-if="pipelineProgress.status === 'processing'">
                    <el-progress 
                        :percentage="pipelineProgress.progress" 
                        :status="pipelineProgress.progress === 100 ? 'success' : null"
                    ></el-progress>
                    <div style="margin-top: 20px; color: #606266;">
                        <p><strong>当前阶段:</strong> {{ getStageName(pipelineProgress.processing_stage) }}</p>
                        <p style="margin-top: 10px; font-size: 13px; color: #909399;">
                            {{ getStageDescription(pipelineProgress.processing_stage) }}
                        </p>
                    </div>
                </div>
                
                <div v-else-if="pipelineProgress.status === 'completed'">
                    <el-result
                        icon="success"
                        title="导入完成"
                        subTitle="PRD 已生成并导入知识库"
                    >
                    </el-result>
                    <div style="text-align: center; margin-top: 20px;">
                        <el-button type="primary" @click="viewPipelineResults">查看结果</el-button>
                        <el-button @click="pipelineProgressVisible = false">关闭</el-button>
                    </div>
                </div>
                
                <div v-else-if="pipelineProgress.status === 'failed'">
                    <el-result
                        icon="error"
                        title="生成失败"
                        :subTitle="pipelineProgress.error_message || '未知错误'"
                    >
                    </el-result>
                    <div style="text-align: center; margin-top: 20px;">
                        <el-button type="primary" @click="retryPipeline">重新运行</el-button>
                        <el-button @click="pipelineProgressVisible = false">关闭</el-button>
                    </div>
                </div>
            </el-dialog>
            
            <!-- 知识库导入结果对话框 -->
            <el-dialog
                title="知识库导入结果"
                :visible.sync="resultsDialogVisible"
                width="90%"
                :append-to-body="true"
                top="5vh"
            >
                <el-tabs v-model="resultsActiveTab">
                    <el-tab-pane label="最终PRD" name="prd">
                        <div v-if="pipelineResults.prd_final" class="markdown-content">
                            <div v-html="renderMarkdown(pipelineResults.prd_final)"></div>
                        </div>
                        <el-empty v-else description="暂无PRD内容"></el-empty>
                    </el-tab-pane>
                    
                    <el-tab-pane label="导入产物" name="files">
                        <el-descriptions :column="1" border>
                            <el-descriptions-item label="doc_id">
                                {{ pipelineResults.doc_id || '-' }}
                            </el-descriptions-item>
                            <el-descriptions-item label="PRD文件">
                                <span v-if="pipelineResults.prd_file_path">
                                    {{ pipelineResults.prd_file_path }}
                                </span>
                                <span v-else>-</span>
                            </el-descriptions-item>
                            <el-descriptions-item label="原文快照">
                                {{ pipelineResults.source_path || '-' }}
                            </el-descriptions-item>
                            <el-descriptions-item label="清洗JSON">
                                {{ pipelineResults.cleaned_json || '-' }}
                            </el-descriptions-item>
                            <el-descriptions-item label="向量JSON">
                                {{ pipelineResults.with_hints_json || '-' }}
                            </el-descriptions-item>
                        </el-descriptions>
                    </el-tab-pane>
                </el-tabs>
            </el-dialog>
        </div>
    `,
    
    data() {
        return {
            // 视图控制
            currentView: 'list',  // 'list' | 'create' | 'detail'
            showGuideDrawer: false, // 控制使用指南抽屉的显示
            
            // 模块列表
            modules: [],
            currentModule: null,
            editingModule: null,
            loading: false,
            
            // 分页
            currentPage: 1,
            pageSize: 20,
            total: 0,
            
            // 表单数据
            moduleForm: {
                name: ''
            },
            notesForm: {
                requirement: ''
            },
            
            // 文件上传
            fileList: [],  // 待上传的文件列表
            uploadedImages: [],  // 已上传的图片
            currentModuleId: null,  // 当前编辑的模块ID
            
            // 图片预览
            previewDialogVisible: false,
            currentPreviewImage: null,
            
            // UI状态
            saving: false,
            
            // 图片流程进度相关
            pipelineProgressVisible: false,
            pipelineProgress: {
                status: 'processing',  // processing/completed/failed
                progress: 0,
                processing_stage: '',
                import_id: null,
                error_message: ''
            },
            progressTimer: null,  // 轮询计时器
            
            // 结果展示
            resultsDialogVisible: false,
            resultsActiveTab: 'prd',
            pipelineResults: {
                prd_final: '',
                prd_file_path: '',
                doc_id: '',
                source_path: '',
                cleaned_json: '',
                with_hints_json: ''
            }
        }
    },
    
    created() {
        // 根据传入的 initialView 设置初始视图
        if (this.initialView) {
            this.currentView = this.initialView;
        }
        // 如果是列表视图，加载模块列表
        if (this.currentView === 'list') {
            this.loadModuleList();
        }
    },
    
    methods: {
        // ==================== 视图切换 ====================
        
        showCreateView() {
            this.currentView = 'create';
            this.editingModule = null;
            this.resetForm();
        },
        
        backToList() {
            // 通知父组件刷新知识库统计和文档列表。
            this.$emit('back-to-parent');
            
            // 组件内部视图切换（用于组件独立使用时）
            this.currentView = 'list';
            this.resetForm();
            this.loadModuleList();
        },
        
        viewModule(module) {
            this.currentModule = module;
            this.currentView = 'detail';
            // 加载完整详情
            this.loadModuleDetail(module.id);
        },
        
        async editModule(module) {
            this.editingModule = module;
            this.currentModuleId = module.id;
            
            // 重新加载完整的模块数据（包括所有图片信息）
            try {
                const response = await axios.get(`/api/requirement-modules/${module.id}`);
                if (response.data.success) {
                    const fullModule = response.data.data;
                    this.moduleForm.name = fullModule.name;
                    this.notesForm.requirement = fullModule.notes_requirement || '';
                    this.uploadedImages = fullModule.images || [];
                } else {
                    // 降级：使用传入的module数据
                    this.moduleForm.name = module.name;
                    this.notesForm.requirement = module.notes_requirement || '';
                    this.uploadedImages = module.images || [];
                }
            } catch (error) {
                console.error('加载模块详情失败:', error);
                // 降级：使用传入的module数据
                this.moduleForm.name = module.name;
                this.notesForm.requirement = module.notes_requirement || '';
                this.uploadedImages = module.images || [];
            }
            
            this.currentView = 'create';
        },
        
        
        // ==================== 模块操作 ====================
        
        async createModuleFirst() {
            try {
                this.loading = true;
                const response = await axios.post('/api/requirement-modules/create', {
                    name: this.moduleForm.name
                });
                
                if (response.data.success) {
                    this.currentModuleId = response.data.data.module_id;
                    this.editingModule = { id: this.currentModuleId };
                    this.$message.success('模块创建成功');
                } else {
                    this.$message.error('创建失败：' + (response.data.error || response.data.message));
                }
            } catch (error) {
                this.$message.error('创建失败：' + error.message);
            } finally {
                this.loading = false;
            }
        },
        
        async uploadImagesToServer() {
            if (this.fileList.length === 0 && this.uploadedImages.length === 0) {
                this.$message.warning('请至少上传一张图片');
                return;
            }
            
            if (this.fileList.length > 0) {
                try {
                    this.loading = true;
                    const formData = new FormData();
                    
                    this.fileList.forEach(file => {
                        formData.append('images', file.raw);
                    });
                    
                    const response = await axios.post(
                        `/api/requirement-modules/${this.currentModuleId}/upload-images`,
                        formData,
                        { headers: { 'Content-Type': 'multipart/form-data' } }
                    );
                    
                    if (response.data.success) {
                        this.uploadedImages = this.uploadedImages.concat(response.data.data.images);
                        this.fileList = [];
                        this.$message.success(`成功上传 ${response.data.data.uploaded} 张图片`);
                    }
                } catch (error) {
                    this.$message.error('上传失败：' + error.message);
                    return;
                } finally {
                    this.loading = false;
                }
            }
        },
        
        async saveModule() {
            // 验证基本信息
            if (!this.moduleForm.name.trim()) {
                this.$message.warning('请填写需求大模块名称');
                return;
            }
            
            // 如果是新建模块，先创建
            if (!this.editingModule) {
                try {
                    this.saving = true;
                    const createResponse = await axios.post('/api/requirement-modules/create', {
                        name: this.moduleForm.name
                    });
                    
                    if (!createResponse.data.success) {
                        this.$message.error('创建失败：' + (createResponse.data.error || createResponse.data.message));
                        return;
                    }
                    
                    this.currentModuleId = createResponse.data.data.module_id;
                    this.editingModule = { id: this.currentModuleId };
                } catch (error) {
                    this.$message.error('创建失败：' + error.message);
                    return;
                } finally {
                    this.saving = false;
                }
            }
            
            // 验证图片
            if (this.fileList.length === 0 && this.uploadedImages.length === 0) {
                this.$message.warning('请至少上传一张图片');
                return;
            }
            
            // 如果有待上传的图片，先上传
            if (this.fileList.length > 0) {
                await this.uploadImagesToServer();
            }
            
            // 保存/更新模块信息
            try {
                this.saving = true;
                
                const response = await axios.put(
                    `/api/requirement-modules/${this.currentModuleId}`,
                    {
                        name: this.moduleForm.name,
                        notes_requirement: this.notesForm.requirement || null
                    }
                );
                
                if (response.data.success) {
                    this.$message.success('保存成功');
                    
                    // 提供选项：查看详情或返回列表
                    this.$confirm('保存成功！', '操作成功', {
                        confirmButtonText: '查看详情',
                        cancelButtonText: '返回列表',
                        type: 'success',
                        distinguishCancelAndClose: true
                    }).then(() => {
                        // 点击"查看详情"，重新加载详情页
                        this.currentView = 'detail';
                        this.loadModuleDetail(this.currentModuleId);
                    }).catch(action => {
                        // 点击"返回列表"或关闭
                        if (action === 'cancel') {
                            this.backToList();
                        }
                    });
                }
            } catch (error) {
                this.$message.error('保存失败：' + error.message);
            } finally {
                this.saving = false;
            }
        },
        
        confirmImportToKb() {
            if (!this.currentModule) return;
            
            this.$confirm(
                '确认将该图片需求生成 PRD 并导入知识库吗？', 
                '确认导入知识库', 
                {
                    confirmButtonText: '确认导入',
                    cancelButtonText: '取消',
                    type: 'warning'
                }
            ).then(() => {
                this.startPipeline();
            }).catch(() => {});
        },
        
        // ========== 图片需求导入知识库 ==========

        finishPipelineImportSuccess(data, successMessage) {
            const result = data || {};
            const fallbackModuleId = this.currentModule ? this.currentModule.id : '';

            this.pipelineProgress = {
                status: 'completed',
                progress: 100,
                processing_stage: 'completed',
                import_id: result.doc_id || fallbackModuleId,
                error_message: ''
            };
            this.pipelineResults = {
                prd_final: result.prd_content || '',
                prd_file_path: result.prd_file || result.source_path || '',
                doc_id: result.doc_id || fallbackModuleId,
                source_path: result.source_path || result.source_json_path || '',
                cleaned_json: result.cleaned_json || '',
                with_hints_json: result.with_hints_json || result.source_json_path || ''
            };
            this.$message.success(successMessage || '图片需求已导入知识库');
        },

        getImportErrorMessage(error, fallbackMessage) {
            const responseData = error && error.response ? error.response.data : null;
            if (responseData && typeof responseData === 'object') {
                return responseData.error || responseData.message || fallbackMessage;
            }
            if (responseData && typeof responseData === 'string') {
                return responseData;
            }
            return (error && error.message) || fallbackMessage;
        },

        isRecoverableImportError(error) {
            const status = error && error.response ? error.response.status : null;
            return !error.response
                || error.code === 'ECONNABORTED'
                || error.code === 'ERR_NETWORK'
                || status === 408
                || status === 502
                || status === 503
                || status === 504;
        },

        async fetchImportedKbDocument(moduleId) {
            if (!moduleId) return null;
            const response = await axios.get('/api/kb/v1/documents', {
                params: { _t: Date.now() },
                timeout: 30000
            });
            const documents = response.data && response.data.data
                ? (response.data.data.documents || [])
                : [];
            return documents.find(doc => doc.doc_id === moduleId) || null;
        },

        async waitForImportedKbDocument(moduleId, timeoutMs, intervalMs) {
            const deadline = Date.now() + (timeoutMs || 10 * 60 * 1000);
            const interval = intervalMs || 5000;

            while (Date.now() < deadline) {
                try {
                    const doc = await this.fetchImportedKbDocument(moduleId);
                    if (doc) {
                        return doc;
                    }
                } catch (error) {
                    console.warn('核验知识库导入状态失败:', error);
                }
                await new Promise(resolve => setTimeout(resolve, interval));
            }
            return null;
        },

        async recoverCompletedImportIfPossible(error, moduleId) {
            if (!this.isRecoverableImportError(error)) {
                return null;
            }

            this.pipelineProgress = {
                status: 'processing',
                progress: 85,
                processing_stage: 'verifying_import',
                import_id: moduleId,
                error_message: ''
            };

            return await this.waitForImportedKbDocument(moduleId, 10 * 60 * 1000, 5000);
        },
        
        async startPipeline() {
            const moduleId = this.currentModule ? this.currentModule.id : null;
            if (!moduleId) {
                this.$message.warning('请选择需要导入的图片需求模块');
                return;
            }

            this.pipelineProgress = {
                status: 'processing',
                progress: 15,
                processing_stage: 'importing_kb',
                import_id: moduleId,
                error_message: ''
            };
            this.pipelineProgressVisible = true;
            this.resultsDialogVisible = false;
            this.resultsActiveTab = 'prd';
            
            try {
                const response = await axios.post('/api/kb/v1/documents/import-image-module', {
                    module_id: moduleId
                }, {
                    timeout: 15 * 60 * 1000
                });
                
                if (response.data.success) {
                    const data = response.data.data || {};
                    this.finishPipelineImportSuccess(data, '图片需求已导入知识库');
                    await this.loadModuleList();
                    await this.loadModuleDetail(moduleId);
                } else {
                    const errorMessage = response.data.error || response.data.message || '导入失败';
                    this.pipelineProgress = {
                        status: 'failed',
                        progress: 0,
                        processing_stage: 'failed',
                        import_id: moduleId,
                        error_message: errorMessage
                    };
                    this.$message.error(errorMessage);
                }
            } catch (error) {
                console.error('导入图片需求失败:', error);

                const importedDoc = await this.recoverCompletedImportIfPossible(error, moduleId);
                if (importedDoc) {
                    this.finishPipelineImportSuccess({
                        doc_id: importedDoc.doc_id,
                        source_json_path: importedDoc.source_json_path
                    }, '后台导入已完成，页面已同步状态');
                    await this.loadModuleList();
                    await this.loadModuleDetail(moduleId);
                    return;
                }

                const errorMessage = this.getImportErrorMessage(error, '导入失败，请检查网络或联系管理员。');
                this.pipelineProgress = {
                    status: 'failed',
                    progress: 0,
                    processing_stage: 'failed',
                    import_id: moduleId,
                    error_message: errorMessage
                };
                this.$message.error(errorMessage);
            }
        },
        
        // 从失败对话框中重试
        retryPipeline() {
            this.pipelineProgressVisible = false;
            this.$nextTick(() => {
                this.startPipeline();
            });
        },
        
        // 从列表中重试失败的模块
        retryModule(module) {
            this.$confirm(
                `确认重新导入 "${module.name}" 到知识库吗？`, 
                '重新导入', 
                {
                    confirmButtonText: '确定',
                    cancelButtonText: '取消',
                    type: 'warning'
                }
            ).then(async () => {
                // 设置当前模块并启动
                this.currentModule = module;
                await this.startPipeline();
            }).catch(() => {});
        },
        
        startProgressPolling() {
            // 清除已有计时器
            if (this.progressTimer) {
                clearInterval(this.progressTimer);
            }
            
            // 立即查询一次
            this.fetchProgress();
            
            // 每2秒查询一次进度
            this.progressTimer = setInterval(() => {
                this.fetchProgress();
            }, 2000);
        },
        
        async fetchProgress() {
            // 当前知识库导入接口为同步执行，不再依赖旧图片流水线轮询接口。
        },
        
        stopProgressPolling() {
            if (this.progressTimer) {
                clearInterval(this.progressTimer);
                this.progressTimer = null;
            }
        },
        
        async viewPipelineResults() {
            this.pipelineProgressVisible = false;
            this.resultsDialogVisible = true;
            this.resultsActiveTab = 'prd';
        },
        
        getStageName(stage) {
            const stageNames = {
                'initializing': '初始化',
                'analyzing_images': '图片分析',
                'generating_prd': 'PRD生成',
                'importing_kb': '导入知识库',
                'saving_results': '结果保存',
                'completed': '已完成'
            };
            return stageNames[stage] || stage;
        },
        
        getStageDescription(stage) {
            const descriptions = {
                'initializing': '正在准备分析环境...',
                'analyzing_images': '正在使用AI分析上传的图片，识别功能需求...',
                'generating_prd': '正在根据图片分析结果生成知识库源文档...',
                'importing_kb': '正在分析图片、生成源文档、清洗知识单元并写入向量库...',
                'verifying_import': '请求连接已中断，正在核验后台是否已经完成导入...',
                'saving_results': '正在保存生成结果...',
                'completed': '知识库导入已完成！'
            };
            return descriptions[stage] || '处理中...';
        },
        
        renderMarkdown(content) {
            if (!content) return '';
            // 简单的Markdown渲染
            return marked.parse(content);
        },
        
        deleteModuleConfirm(module) {
            this.$confirm(
                `确定要删除需求模块"${module.name}"吗？此操作将删除所有图片和数据。`, 
                '警告', 
                {
                    confirmButtonText: '确定',
                    cancelButtonText: '取消',
                    type: 'warning'
                }
            ).then(() => {
                this.deleteModule(module.id);
            }).catch(() => {});
        },
        
        async deleteModule(moduleId) {
            try {
                const response = await axios.delete(`/api/requirement-modules/${moduleId}`);
                
                if (response.data.success) {
                    this.$message.success('删除成功');
                    this.loadModuleList();
                }
            } catch (error) {
                this.$message.error('删除失败：' + error.message);
            }
        },
        
        async deleteUploadedImage(imageId) {
            if (!this.currentModuleId) return;
            
            try {
                const response = await axios.delete(
                    `/api/requirement-modules/${this.currentModuleId}/images/${imageId}`
                );
                
                if (response.data.success) {
                    this.$message.success('删除成功');
                    this.uploadedImages = this.uploadedImages.filter(img => img.id !== imageId);
                }
            } catch (error) {
                this.$message.error('删除失败：' + error.message);
            }
        },
        
        // ==================== 数据加载 ====================
        
        async loadModuleList() {
            this.loading = true;
            
            try {
                const response = await axios.get('/api/requirement-modules', {
                    params: {
                        page: this.currentPage,
                        limit: this.pageSize
                    }
                });
                
                if (response.data.success) {
                    this.modules = response.data.data.modules;
                    this.total = response.data.data.total;
                }
            } catch (error) {
                this.$message.error('加载模块列表失败：' + error.message);
            } finally {
                this.loading = false;
            }
        },
        
        async loadModuleDetail(moduleId) {
            try {
                const response = await axios.get(`/api/requirement-modules/${moduleId}`);
                
                if (response.data.success) {
                    this.currentModule = response.data.data;
                }
            } catch (error) {
                this.$message.error('加载模块详情失败：' + error.message);
            }
        },
        
        // ==================== 文件处理 ====================
        
        handleFileChange(file, fileList) {
            this.fileList = fileList;
        },
        
        handleFileRemove(file, fileList) {
            this.fileList = fileList;
        },
        
        previewImage(img) {
            this.currentPreviewImage = img;
            this.previewDialogVisible = true;
        },
        
        getImagePreviewUrl(img) {
            // 优先使用URL字段
            if (img.url) {
                return img.url;
            }
            // 如果有path字段，转换为URL
            if (img.path) {
                // 处理Windows路径分隔符
                const normalizedPath = img.path.replace(/\\/g, '/');
                // 确保路径以/开头
                return normalizedPath.startsWith('/') ? normalizedPath : '/' + normalizedPath;
            }
            // 本地预览（上传但未保存的图片）
            if (img.raw) {
                return URL.createObjectURL(img.raw);
            }
            return '';
        },
        
        // ==================== 工具方法 ====================
        
        handlePageChange(page) {
            this.currentPage = page;
            this.loadModuleList();
        },
        
        handleRowClick(row) {
            this.viewModule(row);
        },
        
        resetForm() {
            this.moduleForm = { name: '' };
            this.notesForm = { requirement: '' };
            this.fileList = [];
            this.uploadedImages = [];
            this.currentModuleId = null;
        },
        
        hasNotes(module) {
            return !!module.notes_requirement;
        },
        
        getStatusType(status) {
            const typeMap = {
                'draft': 'info',
                'processing': 'warning',
                'completed': 'success',
                'failed': 'danger'
            };
            return typeMap[status] || 'info';
        },
        
        getStatusText(status) {
            const textMap = {
                'draft': '草稿',
                'processing': '生成中',
                'completed': '已完成',
                'failed': '失败'
            };
            return textMap[status] || status;
        },
        
        formatDateTime(dateStr) {
            if (!dateStr) return '-';
            const date = new Date(dateStr);
            return date.toLocaleString('zh-CN');
        },
        
        formatFileSize(bytes) {
            if (!bytes) return '-';
            if (bytes < 1024) return bytes + ' B';
            if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB';
            return (bytes / 1024 / 1024).toFixed(2) + ' MB';
        }
    },
    
    beforeDestroy() {
        // 清理轮询计时器
        this.stopProgressPolling();
    }
});

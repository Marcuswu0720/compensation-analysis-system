import { useEffect, useState } from 'react';
import { Alert, Button, Card, DatePicker, Form, Input, InputNumber, Popconfirm, Select, Space, Switch, Table, Tabs, Typography, message } from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import dayjs from 'dayjs';
import { teamsApi, officesApi } from '../../api/org';
import { ruleTemplatesApi } from '../../api/ruleTemplates';
import { leaveApi } from '../../api/leaveOvertime';
import { holidaysApi } from '../../api/reportsHolidays';

function OfficeRuleTab() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { data: teams = [] } = useQuery({ queryKey: ['teams'], queryFn: teamsApi.list });
  const { data: offices = [] } = useQuery({ queryKey: ['offices'], queryFn: officesApi.list });
  const [teamId, setTeamId] = useState<string>();
  const { data: rule } = useQuery({ queryKey: ['office-rule', teamId], queryFn: () => teamsApi.getOfficeRule(teamId!), enabled: !!teamId });
  const [form] = Form.useForm();

  useEffect(() => {
    form.setFieldsValue(
      rule
        ? { ...rule, officeIds: rule.offices.map((o) => o.id) }
        : { startTime: '09:00', endTime: '18:00', lateGraceMinutes: 0, earlyGraceMinutes: 0, officeIds: [] },
    );
  }, [rule, form]);

  const mutation = useMutation({
    mutationFn: (values: any) => teamsApi.setOfficeRule(teamId!, values),
    onSuccess: () => {
      message.success(t('adminRules.saveSuccess'));
      queryClient.invalidateQueries({ queryKey: ['office-rule', teamId] });
    },
  });

  return (
    <div style={{ maxWidth: 480 }}>
      <Select style={{ width: 240, marginBottom: 16 }} placeholder={t('adminRules.selectTeamOffice')} value={teamId} onChange={setTeamId} options={teams.map((tm) => ({ value: tm.id, label: tm.name }))} />
      {teamId && (
        <Form layout="vertical" form={form} onFinish={(v) => mutation.mutate(v)}>
          <Form.Item name="startTime" label={t('adminRules.startTime')} rules={[{ required: true }]}>
            <Input placeholder="09:00" />
          </Form.Item>
          <Form.Item name="endTime" label={t('adminRules.endTime')} rules={[{ required: true }]}>
            <Input placeholder="18:00" />
          </Form.Item>
          <Form.Item name="lateGraceMinutes" label={t('adminRules.lateGrace')} rules={[{ required: true }]}>
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="earlyGraceMinutes" label={t('adminRules.earlyGrace')} rules={[{ required: true }]}>
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="officeIds" label={t('adminRules.associatedOffices')} help={t('adminRules.associatedOfficesHelp')}>
            <Select mode="multiple" allowClear options={offices.map((o) => ({ value: o.id, label: `${o.name} (±${o.allowedRadiusMeters}m)` }))} />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={mutation.isPending}>
            {t('common.save')}
          </Button>
        </Form>
      )}
    </div>
  );
}

function RuleTemplateTab() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { data: teams = [] } = useQuery({ queryKey: ['teams'], queryFn: teamsApi.list });
  const { data: allOffices = [] } = useQuery({ queryKey: ['offices'], queryFn: officesApi.list });
  const [teamId, setTeamId] = useState<string>();
  const { data: template } = useQuery({ queryKey: ['rule-template', teamId], queryFn: () => ruleTemplatesApi.get(teamId!), enabled: !!teamId });
  const { data: officeRule } = useQuery({ queryKey: ['office-rule', teamId], queryFn: () => teamsApi.getOfficeRule(teamId!), enabled: !!teamId });
  const [form] = Form.useForm();
  const officeAssignmentMode = Form.useWatch('officeAssignmentMode', form);
  // 仅在"已保存的团队规则模板"明确要求标准打卡（非拍照流程、且指定了办公室分配方式）时才提示，
  // 避免对排班打卡等团队因表单默认值误报（问题反馈 2.3：地催团队正是这种配置组合导致遗漏了办公室打卡规则）
  const missingOfficeRule =
    !!template && template.requiresClockIn && !template.requiresPhoto && template.officeAssignmentMode !== 'NONE' && officeRule === null;

  useEffect(() => {
    form.setFieldsValue(
      template
        ? { ...template, officeIds: template.offices.map((o) => o.id) }
        : {
            requiresClockIn: true,
            requiresClockOut: true,
            requiresPhoto: false,
            requiresBusinessMetric: false,
            officeAssignmentMode: 'NONE',
            officeIds: [],
          },
    );
  }, [template, form]);

  const mutation = useMutation({
    mutationFn: (values: any) => ruleTemplatesApi.upsert(teamId!, values),
    onSuccess: () => {
      message.success(t('adminRules.saveSuccess'));
      queryClient.invalidateQueries({ queryKey: ['rule-template', teamId] });
    },
  });

  const removeMutation = useMutation({
    mutationFn: () => ruleTemplatesApi.remove(teamId!),
    onSuccess: () => {
      message.success(t('adminRules.resetSuccess'));
      queryClient.invalidateQueries({ queryKey: ['rule-template', teamId] });
    },
  });

  return (
    <div style={{ maxWidth: 480 }}>
      <Typography.Paragraph type="secondary">{t('adminRules.templateDesc')}</Typography.Paragraph>
      <Select style={{ width: 240, marginBottom: 16 }} placeholder={t('adminRules.selectTeam')} value={teamId} onChange={setTeamId} options={teams.map((tm) => ({ value: tm.id, label: tm.name }))} />
      {teamId && (
        <Alert
          type={template ? 'warning' : 'info'}
          showIcon
          style={{ marginBottom: 16 }}
          message={template ? t('adminRules.templateOverrideActive') : t('adminRules.templateNoOverride')}
        />
      )}
      {missingOfficeRule && (
        <Alert type="error" showIcon style={{ marginBottom: 16 }} message={t('adminRules.missingOfficeRuleWarning')} />
      )}
      {teamId && (
        <Form layout="vertical" form={form} onFinish={(v) => mutation.mutate(v)}>
          <Form.Item name="requiresClockIn" label={t('adminRules.requiresClockIn')} valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="requiresClockOut" label={t('adminRules.requiresClockOut')} valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="requiresPhoto" label={t('adminRules.requiresPhoto')} valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="photoIntervalThresholdMinutes" label={t('adminRules.photoIntervalThreshold')}>
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="photoIntervalPreWarnMinutes" label={t('adminRules.photoIntervalPreWarn')} help={t('adminRules.photoIntervalPreWarnHelp')}>
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="requiresBusinessMetric" label={t('adminRules.requiresBusinessMetric')} valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="businessMetricThreshold" label={t('adminRules.businessMetricThreshold')}>
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="businessMetricSource" label={t('adminRules.businessMetricSource')}>
            <Select
              allowClear
              options={[
                { value: 'MANUAL', label: t('adminRules.sourceManual') },
                { value: 'API', label: t('adminRules.sourceApi') },
              ]}
            />
          </Form.Item>
          <Form.Item name="officeAssignmentMode" label={t('adminRules.officeAssignmentMode')}>
            <Select
              options={[
                { value: 'NONE', label: t('adminRules.assignNone') },
                { value: 'NEAREST_AUTO', label: t('adminRules.assignNearest') },
                { value: 'FIXED', label: t('adminRules.assignFixed') },
              ]}
            />
          </Form.Item>
          {officeAssignmentMode === 'FIXED' && (
            <Form.Item name="officeIds" label={t('adminRules.fixedOffices')} help={t('adminRules.fixedOfficesHelp')}>
              <Select mode="multiple" allowClear options={allOffices.map((o) => ({ value: o.id, label: `${o.name} (±${o.allowedRadiusMeters}m)` }))} />
            </Form.Item>
          )}
          <Space>
            <Button type="primary" htmlType="submit" loading={mutation.isPending}>
              {t('common.save')}
            </Button>
            {template && (
              <Popconfirm title={t('adminRules.resetConfirm')} onConfirm={() => removeMutation.mutate()}>
                <Button danger loading={removeMutation.isPending}>
                  {t('adminRules.resetToDefault')}
                </Button>
              </Popconfirm>
            )}
          </Space>
        </Form>
      )}
    </div>
  );
}

function LeaveTypesTab() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { data = [] } = useQuery({ queryKey: ['leave-types-all'], queryFn: () => leaveApi.types(false) });
  const [form] = Form.useForm();

  const createMutation = useMutation({
    mutationFn: leaveApi.createType,
    onSuccess: () => {
      message.success(t('common.createSuccess'));
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['leave-types-all'] });
    },
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, isActive }: { id: string; isActive: boolean }) => leaveApi.setTypeActive(id, isActive),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['leave-types-all'] }),
  });

  return (
    <div>
      <Form layout="inline" form={form} onFinish={(v) => createMutation.mutate(v)} style={{ marginBottom: 16 }}>
        <Form.Item name="code" rules={[{ required: true }]}>
          <Input placeholder={t('adminRules.typeCodePlaceholder')} />
        </Form.Item>
        <Form.Item name="name" rules={[{ required: true }]}>
          <Input placeholder={t('adminRules.typeNamePlaceholder')} />
        </Form.Item>
        <Form.Item name="nameEn">
          <Input placeholder={t('adminRules.typeNameEnPlaceholder')} />
        </Form.Item>
        <Button type="primary" htmlType="submit" loading={createMutation.isPending}>
          {t('adminRules.addLeaveType')}
        </Button>
      </Form>
      <Table
        rowKey="id"
        scroll={{ x: "max-content" }}
        dataSource={data}
        columns={[
          { title: t('adminRules.typeCode'), dataIndex: 'code' },
          { title: t('adminRules.typeName'), dataIndex: 'name' },
          { title: t('adminRules.typeNameEn'), dataIndex: 'nameEn' },
          {
            title: t('adminRules.active'),
            dataIndex: 'isActive',
            render: (v, r) => <Switch checked={v} onChange={(checked) => toggleMutation.mutate({ id: r.id, isActive: checked })} />,
          },
        ]}
      />
    </div>
  );
}

function HolidaysTab() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [year, setYear] = useState(dayjs().year().toString());
  const { data = [] } = useQuery({ queryKey: ['holidays', year], queryFn: () => holidaysApi.list(year) });
  const [form] = Form.useForm();

  const createMutation = useMutation({
    mutationFn: (v: any) => holidaysApi.create({ date: v.date.format('YYYY-MM-DD'), name: v.name, isWorkday: v.isWorkday }),
    onSuccess: () => {
      message.success(t('common.createSuccess'));
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['holidays', year] });
    },
  });

  const removeMutation = useMutation({
    mutationFn: holidaysApi.remove,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['holidays', year] }),
  });

  return (
    <div>
      <DatePicker picker="year" onChange={(v) => v && setYear(v.year().toString())} style={{ marginBottom: 16 }} />
      <Form layout="inline" form={form} onFinish={(v) => createMutation.mutate(v)} style={{ marginBottom: 16 }}>
        <Form.Item name="date" rules={[{ required: true }]}>
          <DatePicker placeholder={t('adminRules.holidayDate')} />
        </Form.Item>
        <Form.Item name="name" rules={[{ required: true }]}>
          <Input placeholder={t('adminRules.holidayNamePlaceholder')} />
        </Form.Item>
        <Form.Item name="isWorkday" valuePropName="checked" initialValue={false}>
          <Switch checkedChildren={t('adminRules.workday')} unCheckedChildren={t('adminRules.statutoryHoliday')} />
        </Form.Item>
        <Button type="primary" htmlType="submit" loading={createMutation.isPending}>
          {t('adminRules.addHoliday')}
        </Button>
      </Form>
      <Table
        rowKey="id"
        scroll={{ x: "max-content" }}
        dataSource={data}
        columns={[
          { title: t('adminRules.date'), dataIndex: 'date', render: (v) => dayjs(v).format('YYYY-MM-DD') },
          { title: t('adminRules.typeName'), dataIndex: 'name' },
          { title: t('adminRules.typeCol'), dataIndex: 'isWorkday', render: (v) => (v ? t('adminRules.workday') : t('adminRules.statutoryHoliday')) },
          {
            title: t('common.actions'),
            render: (_, r: any) => (
              <Popconfirm title={t('adminRules.deleteConfirm')} onConfirm={() => removeMutation.mutate(r.id)}>
                <Button size="small" danger>
                  {t('common.delete')}
                </Button>
              </Popconfirm>
            ),
          },
        ]}
      />
    </div>
  );
}

export default function Rules() {
  const { t } = useTranslation();
  return (
    <div>
      <Typography.Title level={3}>{t('adminRules.title')}</Typography.Title>
      <Card>
        <Tabs
          items={[
            { key: 'office', label: t('adminRules.officeRuleTab'), children: <OfficeRuleTab /> },
            { key: 'ruleTemplate', label: t('adminRules.ruleTemplateTab'), children: <RuleTemplateTab /> },
            { key: 'leaveTypes', label: t('adminRules.leaveTypesTab'), children: <LeaveTypesTab /> },
            { key: 'holidays', label: t('adminRules.holidaysTab'), children: <HolidaysTab /> },
          ]}
        />
      </Card>
    </div>
  );
}

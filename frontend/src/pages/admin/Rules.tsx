import { useEffect, useState } from 'react';
import { Button, Card, DatePicker, Form, Input, InputNumber, Popconfirm, Select, Switch, Table, Tabs, Typography, message } from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { teamsApi } from '../../api/org';
import { ruleTemplatesApi } from '../../api/ruleTemplates';
import { leaveApi } from '../../api/leaveOvertime';
import { holidaysApi } from '../../api/reportsHolidays';

function OfficeRuleTab() {
  const queryClient = useQueryClient();
  const { data: teams = [] } = useQuery({ queryKey: ['teams'], queryFn: teamsApi.list });
  const [teamId, setTeamId] = useState<string>();
  const { data: rule } = useQuery({ queryKey: ['office-rule', teamId], queryFn: () => teamsApi.getOfficeRule(teamId!), enabled: !!teamId });
  const [form] = Form.useForm();

  useEffect(() => {
    form.setFieldsValue(rule ?? { startTime: '09:00', endTime: '18:00', lateGraceMinutes: 0, earlyGraceMinutes: 0 });
  }, [rule, form]);

  const mutation = useMutation({
    mutationFn: (values: any) => teamsApi.setOfficeRule(teamId!, values),
    onSuccess: () => {
      message.success('保存成功');
      queryClient.invalidateQueries({ queryKey: ['office-rule', teamId] });
    },
  });

  return (
    <div style={{ maxWidth: 480 }}>
      <Select style={{ width: 240, marginBottom: 16 }} placeholder="选择团队（办公室打卡模式）" value={teamId} onChange={setTeamId} options={teams.map((t) => ({ value: t.id, label: t.name }))} />
      {teamId && (
        <Form layout="vertical" form={form} onFinish={(v) => mutation.mutate(v)}>
          <Form.Item name="startTime" label="上班时间 (HH:mm)" rules={[{ required: true }]}>
            <Input placeholder="09:00" />
          </Form.Item>
          <Form.Item name="endTime" label="下班时间 (HH:mm)" rules={[{ required: true }]}>
            <Input placeholder="18:00" />
          </Form.Item>
          <Form.Item name="lateGraceMinutes" label="迟到宽限（分钟）" rules={[{ required: true }]}>
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="earlyGraceMinutes" label="早退宽限（分钟）" rules={[{ required: true }]}>
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={mutation.isPending}>
            保存
          </Button>
        </Form>
      )}
    </div>
  );
}

function RuleTemplateTab() {
  const queryClient = useQueryClient();
  const { data: teams = [] } = useQuery({ queryKey: ['teams'], queryFn: teamsApi.list });
  const [teamId, setTeamId] = useState<string>();
  const { data: template } = useQuery({ queryKey: ['rule-template', teamId], queryFn: () => ruleTemplatesApi.get(teamId!), enabled: !!teamId });
  const [form] = Form.useForm();

  useEffect(() => {
    form.setFieldsValue(
      template ?? {
        requiresClockIn: true,
        requiresClockOut: true,
        requiresPhoto: false,
        requiresBusinessMetric: false,
        officeAssignmentMode: 'NONE',
      },
    );
  }, [template, form]);

  const mutation = useMutation({
    mutationFn: (values: any) => ruleTemplatesApi.upsert(teamId!, values),
    onSuccess: () => {
      message.success('保存成功');
      queryClient.invalidateQueries({ queryKey: ['rule-template', teamId] });
    },
  });

  return (
    <div style={{ maxWidth: 480 }}>
      <Typography.Paragraph type="secondary">
        7.3节团队级细分打卡规则模板：按团队/岗位维度配置是否打卡/是否需要照片/是否需要业务指标考核，覆盖地催、码牌、面签等场景。
      </Typography.Paragraph>
      <Select style={{ width: 240, marginBottom: 16 }} placeholder="选择团队" value={teamId} onChange={setTeamId} options={teams.map((t) => ({ value: t.id, label: t.name }))} />
      {teamId && (
        <Form layout="vertical" form={form} onFinish={(v) => mutation.mutate(v)}>
          <Form.Item name="requiresClockIn" label="需要上班打卡" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="requiresClockOut" label="需要下班打卡" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="requiresPhoto" label="需要拍照/GPS轨迹" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="photoIntervalThresholdMinutes" label="照片间隔预警阈值（分钟）">
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="requiresBusinessMetric" label="需要业务指标判断出勤" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="businessMetricThreshold" label="业务指标阈值（如部署商户数）">
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="businessMetricSource" label="业务指标来源">
            <Select
              allowClear
              options={[
                { value: 'MANUAL', label: '人工录入' },
                { value: 'API', label: 'API对接（待确认）' },
              ]}
            />
          </Form.Item>
          <Form.Item name="officeAssignmentMode" label="办公室分配方式">
            <Select
              options={[
                { value: 'NONE', label: '不涉及' },
                { value: 'NEAREST_AUTO', label: '最近办公室自动分配' },
                { value: 'FIXED', label: '固定办公室' },
              ]}
            />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={mutation.isPending}>
            保存
          </Button>
        </Form>
      )}
    </div>
  );
}

function LeaveTypesTab() {
  const queryClient = useQueryClient();
  const { data = [] } = useQuery({ queryKey: ['leave-types-all'], queryFn: () => leaveApi.types(false) });
  const [form] = Form.useForm();

  const createMutation = useMutation({
    mutationFn: leaveApi.createType,
    onSuccess: () => {
      message.success('创建成功');
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
          <Input placeholder="类型代码，如 PERSONAL" />
        </Form.Item>
        <Form.Item name="name" rules={[{ required: true }]}>
          <Input placeholder="类型名称，如 事假" />
        </Form.Item>
        <Button type="primary" htmlType="submit" loading={createMutation.isPending}>
          新增请假类型
        </Button>
      </Form>
      <Table
        rowKey="id"
        scroll={{ x: "max-content" }}
        dataSource={data}
        columns={[
          { title: '代码', dataIndex: 'code' },
          { title: '名称', dataIndex: 'name' },
          {
            title: '启用',
            dataIndex: 'isActive',
            render: (v, r) => <Switch checked={v} onChange={(checked) => toggleMutation.mutate({ id: r.id, isActive: checked })} />,
          },
        ]}
      />
    </div>
  );
}

function HolidaysTab() {
  const queryClient = useQueryClient();
  const [year, setYear] = useState(dayjs().year().toString());
  const { data = [] } = useQuery({ queryKey: ['holidays', year], queryFn: () => holidaysApi.list(year) });
  const [form] = Form.useForm();

  const createMutation = useMutation({
    mutationFn: (v: any) => holidaysApi.create({ date: v.date.format('YYYY-MM-DD'), name: v.name, isWorkday: v.isWorkday }),
    onSuccess: () => {
      message.success('创建成功');
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
          <DatePicker placeholder="日期" />
        </Form.Item>
        <Form.Item name="name" rules={[{ required: true }]}>
          <Input placeholder="节假日名称" />
        </Form.Item>
        <Form.Item name="isWorkday" valuePropName="checked" initialValue={false}>
          <Switch checkedChildren="调休上班" unCheckedChildren="法定假日" />
        </Form.Item>
        <Button type="primary" htmlType="submit" loading={createMutation.isPending}>
          新增
        </Button>
      </Form>
      <Table
        rowKey="id"
        scroll={{ x: "max-content" }}
        dataSource={data}
        columns={[
          { title: '日期', dataIndex: 'date', render: (v) => dayjs(v).format('YYYY-MM-DD') },
          { title: '名称', dataIndex: 'name' },
          { title: '类型', dataIndex: 'isWorkday', render: (v) => (v ? '调休上班日' : '法定假日') },
          {
            title: '操作',
            render: (_, r: any) => (
              <Popconfirm title="确认删除？" onConfirm={() => removeMutation.mutate(r.id)}>
                <Button size="small" danger>
                  删除
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
  return (
    <div>
      <Typography.Title level={3}>考勤规则配置</Typography.Title>
      <Card>
        <Tabs
          items={[
            { key: 'office', label: '办公室打卡规则', children: <OfficeRuleTab /> },
            { key: 'ruleTemplate', label: '团队级规则模板', children: <RuleTemplateTab /> },
            { key: 'leaveTypes', label: '请假类型管理', children: <LeaveTypesTab /> },
            { key: 'holidays', label: '法定节假日', children: <HolidaysTab /> },
          ]}
        />
      </Card>
    </div>
  );
}

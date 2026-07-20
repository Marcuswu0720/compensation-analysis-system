import { useState } from 'react';
import { Button, Card, Image, Input, Modal, Space, Table, Tabs, Tag, Typography, message, DatePicker, Select } from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { locationCheckinApi } from '../api/locationCheckin';
import { usersApi } from '../api/org';
import { VERIFY_COLOR, VERIFY_LABEL } from '../utils/status';

const API_ORIGIN = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:3000/api').replace(/\/api\/?$/, '');

function PendingTab() {
  const queryClient = useQueryClient();
  const { data = [] } = useQuery({ queryKey: ['location-pending'], queryFn: locationCheckinApi.pending });
  const [modal, setModal] = useState<{ id: string; status: 'APPROVED' | 'REJECTED' } | null>(null);
  const [remark, setRemark] = useState('');

  const mutation = useMutation({
    mutationFn: () => locationCheckinApi.verify(modal!.id, modal!.status, remark),
    onSuccess: () => {
      message.success('已核实');
      setModal(null);
      setRemark('');
      queryClient.invalidateQueries({ queryKey: ['location-pending'] });
    },
  });

  return (
    <>
      <Table
        rowKey="id"
        dataSource={data}
        columns={[
          { title: '照片', dataIndex: 'photoUrl', render: (v) => <Image src={`${API_ORIGIN}${v}`} width={80} /> },
          { title: '员工', render: (_, r: any) => `${r.user?.name}(${r.user?.employeeNo})` },
          { title: '团队', render: (_, r: any) => r.user?.team?.name },
          { title: '拍摄时间', dataIndex: 'takenAt', render: (v) => dayjs(v).format('YYYY-MM-DD HH:mm:ss') },
          { title: 'GPS', render: (_, r: any) => `${r.gpsLat.toFixed(4)}, ${r.gpsLng.toFixed(4)}` },
          { title: '业务指标', dataIndex: 'businessMetricValue' },
          {
            title: '操作',
            render: (_, r: any) => (
              <Space>
                <Button size="small" type="primary" onClick={() => setModal({ id: r.id, status: 'APPROVED' })}>
                  通过
                </Button>
                <Button size="small" danger onClick={() => setModal({ id: r.id, status: 'REJECTED' })}>
                  驳回
                </Button>
              </Space>
            ),
          },
        ]}
      />
      <Modal title="核实定位打卡" open={!!modal} onCancel={() => setModal(null)} onOk={() => mutation.mutate()} confirmLoading={mutation.isPending}>
        <Input.TextArea rows={3} placeholder="备注（可选）" value={remark} onChange={(e) => setRemark(e.target.value)} />
      </Modal>
    </>
  );
}

function TrajectoryTab() {
  const [userId, setUserId] = useState<string>();
  const [date, setDate] = useState(dayjs());
  const { data: users = [] } = useQuery({ queryKey: ['users-all'], queryFn: () => usersApi.list() });
  const { data = [] } = useQuery({
    queryKey: ['trajectory', userId, date.format('YYYY-MM-DD')],
    queryFn: () => locationCheckinApi.trajectory(userId!, date.format('YYYY-MM-DD')),
    enabled: !!userId,
  });

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Select
          style={{ width: 240 }}
          placeholder="选择员工"
          value={userId}
          onChange={setUserId}
          options={users.map((u) => ({ value: u.id, label: `${u.name}(${u.employeeNo})` }))}
          showSearch
          filterOption={(input, option) => (option?.label as string).toLowerCase().includes(input.toLowerCase())}
        />
        <DatePicker value={date} onChange={(v) => v && setDate(v)} />
      </Space>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        {data.map((photo, idx) => (
          <Card key={photo.id} size="small" style={{ width: 180 }} title={`#${idx + 1} ${dayjs(photo.takenAt).format('HH:mm:ss')}`}>
            <Image src={`${API_ORIGIN}${photo.photoUrl}`} width={150} />
            <div style={{ marginTop: 8 }}>
              <Tag color={VERIFY_COLOR[photo.verifyStatus]}>{VERIFY_LABEL[photo.verifyStatus]}</Tag>
            </div>
            <div style={{ fontSize: 12, color: '#888' }}>
              {photo.gpsLat.toFixed(4)}, {photo.gpsLng.toFixed(4)}
            </div>
          </Card>
        ))}
        {userId && data.length === 0 && <Typography.Text type="secondary">当日无打卡照片</Typography.Text>}
      </div>
    </div>
  );
}

export default function LocationCheckinReview() {
  return (
    <div>
      <Typography.Title level={3}>定位打卡核实</Typography.Title>
      <Card>
        <Tabs
          items={[
            { key: 'pending', label: '待核实', children: <PendingTab /> },
            { key: 'trajectory', label: '打卡轨迹', children: <TrajectoryTab /> },
          ]}
        />
      </Card>
    </div>
  );
}

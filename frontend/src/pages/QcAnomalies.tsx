import { useState } from 'react';
import { Button, Card, Image, Input, Modal, Select, Table, Tag, Typography, message } from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import dayjs from 'dayjs';
import { locationAnomaliesApi } from '../api/locationAnomalies';
import { PHOTO_FALLBACK } from '../utils/imagePlaceholder';
import type { AnomalyReviewStatus } from '../api/types';
import { useAuthStore } from '../store/authStore';

const API_ORIGIN = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:3000/api').replace(/\/api\/?$/, '');

export default function QcAnomalies() {
  const { t } = useTranslation();
  const user = useAuthStore((s) => s.user);
  const isQc = user?.role === 'QC_TEAM';
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<AnomalyReviewStatus | undefined>('PENDING');
  const { data = [] } = useQuery({ queryKey: ['location-anomalies', status], queryFn: () => locationAnomaliesApi.list(status) });
  const [reviewTarget, setReviewTarget] = useState<string | null>(null);
  const [reviewNote, setReviewNote] = useState('');

  const mutation = useMutation({
    mutationFn: () => locationAnomaliesApi.review(reviewTarget!, reviewNote || undefined),
    onSuccess: () => {
      message.success(t('qcAnomalies.reviewSuccess'));
      setReviewTarget(null);
      setReviewNote('');
      queryClient.invalidateQueries({ queryKey: ['location-anomalies'] });
    },
    onError: (e: any) => message.error(e?.response?.data?.message ?? t('common.opFailed')),
  });

  return (
    <div>
      <Typography.Title level={3}>{t('qcAnomalies.title')}</Typography.Title>
      <Card>
        <Select
          style={{ width: 160, marginBottom: 16 }}
          value={status}
          onChange={setStatus}
          allowClear
          placeholder={t('qcAnomalies.allStatuses')}
          options={[
            { value: 'PENDING', label: t('qcAnomalies.pending') },
            { value: 'REVIEWED', label: t('qcAnomalies.reviewed') },
          ]}
        />
        <Table
          rowKey="id"
          scroll={{ x: 'max-content' }}
          dataSource={data}
          columns={[
            { title: t('locationCheckinReview.photo'), render: (_, r) => <Image src={`${API_ORIGIN}${r.photo.photoUrl}`} width={80} fallback={PHOTO_FALLBACK} /> },
            { title: t('common.employee'), render: (_, r) => `${r.user.name}(${r.user.employeeNo})` },
            { title: t('common.team'), render: (_, r) => r.user.team?.name },
            { title: t('qcAnomalies.interval'), render: (_, r) => `${r.intervalMinutes} / ${r.thresholdMinutes} min` },
            { title: t('locationCheckinReview.takenAt'), render: (_, r) => dayjs(r.photo.takenAt).format('YYYY-MM-DD HH:mm:ss') },
            {
              title: t('common.status'),
              dataIndex: 'status',
              render: (v: AnomalyReviewStatus) => (v === 'PENDING' ? <Tag color="gold">{t('qcAnomalies.pending')}</Tag> : <Tag color="green">{t('qcAnomalies.reviewed')}</Tag>),
            },
            { title: t('qcAnomalies.reviewNote'), dataIndex: 'reviewNote' },
            ...(isQc
              ? [
                  {
                    title: t('common.actions'),
                    render: (_: unknown, r: any) =>
                      r.status === 'PENDING' ? (
                        <Button size="small" type="primary" onClick={() => setReviewTarget(r.id)}>
                          {t('qcAnomalies.markReviewed')}
                        </Button>
                      ) : null,
                  },
                ]
              : []),
          ]}
        />
      </Card>
      <Modal
        title={t('qcAnomalies.markReviewed')}
        open={!!reviewTarget}
        onCancel={() => setReviewTarget(null)}
        onOk={() => mutation.mutate()}
        confirmLoading={mutation.isPending}
      >
        <Input.TextArea rows={3} placeholder={t('qcAnomalies.reviewNotePlaceholder')} value={reviewNote} onChange={(e) => setReviewNote(e.target.value)} />
      </Modal>
    </div>
  );
}

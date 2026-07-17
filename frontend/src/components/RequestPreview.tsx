import React, { useMemo } from 'react';
import { Card, Typography, Button, Space, Tooltip, message } from 'antd';
import { CopyOutlined } from '@ant-design/icons';

interface RequestPreviewProps {
  method: string;
  url: string;
  headers: Record<string, string>;
  body: any;
  height?: number | string;
}

const { Text } = Typography;

const RequestPreview: React.FC<RequestPreviewProps> = ({ method, url, headers, body, height = '100%' }) => {
  const formattedBody = useMemo(() => {
    try {
      return JSON.stringify(body, null, 2);
    } catch {
      return String(body);
    }
  }, [body]);

  const fullRequestText = useMemo(() => {
    let text = `${method.toUpperCase()} ${url}\n\n`;
    text += 'Headers:\n';
    for (const [k, v] of Object.entries(headers)) {
      text += `  ${k}: ${v}\n`;
    }
    text += `\nBody:\n${formattedBody}`;
    return text;
  }, [method, url, headers, formattedBody]);

  const handleCopy = () => {
    navigator.clipboard.writeText(fullRequestText);
    message.success('已复制请求 JSON');
  };

  return (
    <Card
      size="small"
      title={
        <Space size={4}>
          <Text code style={{ fontSize: 12 }}>{method.toUpperCase()}</Text>
          <Text style={{ fontSize: 12 }}>{url || '(未填写 API 地址)'}</Text>
        </Space>
      }
      extra={
        <Tooltip title="复制完整请求">
          <Button size="small" icon={<CopyOutlined />} onClick={handleCopy} />
        </Tooltip>
      }
      style={{ height, display: 'flex', flexDirection: 'column' }}
      styles={{ body: { flex: 1, overflow: 'auto', padding: 12 } }}
    >
      <div style={{ fontFamily: 'var(--font-family-mono, monospace)', fontSize: 12, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
        <Text type="secondary" style={{ fontSize: 11 }}>Headers</Text>
        {Object.keys(headers).length === 0 ? (
          <div style={{ color: '#bbb', padding: '4px 0' }}>（无自定义请求头）</div>
        ) : (
          Object.entries(headers).map(([k, v]) => (
            <div key={k} style={{ padding: '1px 0' }}>
              <Text style={{ color: '#0550ae' }}>{k}: </Text>
              <Text style={{ color: '#656d76' }}>{v}</Text>
            </div>
          ))
        )}
        <div style={{ borderTop: '1px solid #eee', margin: '8px 0' }} />
        <Text type="secondary" style={{ fontSize: 11 }}>Body</Text>
        <pre style={{
          margin: '4px 0 0 0',
          padding: 8,
          background: '#f6f8fa',
          borderRadius: 4,
          fontSize: 12,
          lineHeight: 1.5,
          overflow: 'auto',
          maxHeight: height === '100%' ? 400 : `calc(${typeof height === 'number' ? height : 400}px - 120px)`,
        }}>
          {formattedBody || '(空)'}
        </pre>
      </div>
    </Card>
  );
};

export default RequestPreview;

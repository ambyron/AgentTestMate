import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import App from './App';
import './index.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <ConfigProvider
        locale={zhCN}
        theme={{
          token: {
            colorPrimary: '#111827',
            colorBgLayout: '#F3F4F6',
            borderRadius: 6,
            fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
            colorBorder: '#E5E7EB',
            colorBgContainer: '#FFFFFF',
            colorText: '#374151',
            colorTextSecondary: '#6B7280',
            colorTextTertiary: '#9CA3AF',
            colorBgTextHover: '#F3F4F6',
            controlHeight: 32,
            fontSize: 13,
          },
          components: {
            Table: {
              headerBg: '#F9FAFB',
              headerColor: '#9CA3AF',
              headerBorderRadius: 0,
              borderColor: '#F3F4F6',
              rowHoverBg: '#F9FAFB',
            },
            Card: {
              borderRadius: 8,
            },
            Modal: {
              borderRadius: 8,
            },
            Button: {
              borderRadius: 6,
              borderRadiusLG: 6,
              borderRadiusSM: 4,
            },
            Tag: {
              borderRadius: 4,
            },
            Menu: {
              itemBg: 'transparent',
              itemBorderRadius: 6,
            },
            Tabs: {
              inkBarColor: '#111827',
              itemSelectedColor: '#111827',
              itemColor: '#9CA3AF',
              itemHoverColor: '#6B7280',
            },
          },
        }}
      >
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </ConfigProvider>
    </QueryClientProvider>
  </React.StrictMode>
);

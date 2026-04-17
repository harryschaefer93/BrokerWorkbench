import { 
  AreaChart, 
  Area, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui';
import { motion } from 'framer-motion';

const renewalData = [
  { month: 'Jan', policies: 12, premium: 45000 },
  { month: 'Feb', policies: 19, premium: 68000 },
  { month: 'Mar', policies: 15, premium: 52000 },
  { month: 'Apr', policies: 22, premium: 78000 },
  { month: 'May', policies: 18, premium: 61000 },
  { month: 'Jun', policies: 25, premium: 94000 },
];

const policyTypeData = [
  { name: 'Auto', value: 35, color: '#8b5cf6' },
  { name: 'Home', value: 28, color: '#06b6d4' },
  { name: 'Commercial', value: 22, color: '#f59e0b' },
  { name: 'Life', value: 15, color: '#10b981' },
];

export function RenewalTrendChart() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
    >
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Renewal Trend</CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={renewalData}>
              <defs>
                <linearGradient id="colorPremium" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.3}/>
                  <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis 
                dataKey="month" 
                tick={{ fontSize: 11 }} 
                stroke="#9ca3af"
              />
              <YAxis 
                tick={{ fontSize: 11 }} 
                stroke="#9ca3af"
                tickFormatter={(value) => `$${value / 1000}k`}
              />
              <Tooltip 
                contentStyle={{ 
                  borderRadius: '8px', 
                  border: '1px solid #e5e7eb',
                  fontSize: '12px',
                }}
                formatter={(value: number) => [`$${value.toLocaleString()}`, 'Premium']}
              />
              <Area 
                type="monotone" 
                dataKey="premium" 
                stroke="#8b5cf6" 
                strokeWidth={2}
                fillOpacity={1} 
                fill="url(#colorPremium)" 
              />
            </AreaChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </motion.div>
  );
}

export function PolicyDistributionChart() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.1 }}
    >
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Policy Distribution</CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie
                data={policyTypeData}
                cx="50%"
                cy="50%"
                innerRadius={50}
                outerRadius={80}
                paddingAngle={2}
                dataKey="value"
              >
                {policyTypeData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip 
                contentStyle={{ 
                  borderRadius: '8px', 
                  border: '1px solid #e5e7eb',
                  fontSize: '12px',
                }}
                formatter={(value: number) => [`${value}%`, 'Share']}
              />
            </PieChart>
          </ResponsiveContainer>
          <div className="flex flex-wrap justify-center gap-3 mt-2">
            {policyTypeData.map((item) => (
              <div key={item.name} className="flex items-center gap-1.5 text-xs">
                <div 
                  className="w-2.5 h-2.5 rounded-full" 
                  style={{ backgroundColor: item.color }} 
                />
                {item.name}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}

export function CarrierPerformanceChart() {
  const data = [
    { carrier: 'State Farm', quotes: 42, wins: 28 },
    { carrier: 'Allstate', quotes: 38, wins: 22 },
    { carrier: 'Progressive', quotes: 45, wins: 31 },
    { carrier: 'Geico', quotes: 32, wins: 18 },
  ];

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.2 }}
    >
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Carrier Performance</CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis 
                dataKey="carrier" 
                tick={{ fontSize: 10 }} 
                stroke="#9ca3af"
              />
              <YAxis 
                tick={{ fontSize: 11 }} 
                stroke="#9ca3af"
              />
              <Tooltip 
                contentStyle={{ 
                  borderRadius: '8px', 
                  border: '1px solid #e5e7eb',
                  fontSize: '12px',
                }}
              />
              <Bar dataKey="quotes" fill="#e5e7eb" radius={[4, 4, 0, 0]} name="Quotes" />
              <Bar dataKey="wins" fill="#8b5cf6" radius={[4, 4, 0, 0]} name="Wins" />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </motion.div>
  );
}

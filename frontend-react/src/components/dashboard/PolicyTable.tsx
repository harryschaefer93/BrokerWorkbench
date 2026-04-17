import { motion } from 'framer-motion';
import { 
  Table, 
  TableHeader, 
  TableBody, 
  TableHead, 
  TableRow, 
  TableCell,
  Badge,
  Button,
} from '@/components/ui';
import { usePolicies } from '@/hooks';

const statusConfig = {
  active: { variant: 'success' as const, label: 'Active' },
  renewal: { variant: 'warning' as const, label: 'Renewal Due' },
  pending: { variant: 'critical' as const, label: 'Quote Pending' },
  expired: { variant: 'destructive' as const, label: 'Expired' },
};

export function PolicyTable() {
  const { data: policies, loading } = usePolicies();

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
    }).format(value);
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      month: '2-digit',
      day: '2-digit',
      year: 'numeric',
    });
  };

  const getStatus = (policy: typeof policies[0]) => {
    const expiry = new Date(policy.expiration_date);
    const now = new Date();
    const daysUntil = Math.ceil((expiry.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
    
    if (policy.status === 'pending') return 'pending';
    if (daysUntil <= 30) return 'renewal';
    if (daysUntil < 0) return 'expired';
    return 'active';
  };

  if (loading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-16 bg-muted/50 rounded-md animate-pulse" />
        ))}
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
    >
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Policy #</TableHead>
            <TableHead>Client</TableHead>
            <TableHead>Type</TableHead>
            <TableHead>Carrier</TableHead>
            <TableHead>Premium</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Renewal</TableHead>
            <TableHead>Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {policies.map((policy, index) => {
            const status = getStatus(policy);
            const config = statusConfig[status];
            
            return (
              <motion.tr
                key={policy.policy_id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.2, delay: index * 0.05 }}
                className="border-b transition-colors hover:bg-muted/50"
              >
                <TableCell className="font-medium">{policy.policy_id}</TableCell>
                <TableCell>{policy.client_name || policy.client_id}</TableCell>
                <TableCell className="capitalize">{policy.policy_type}</TableCell>
                <TableCell>{policy.carrier_name || policy.carrier_id}</TableCell>
                <TableCell>{formatCurrency(policy.premium)}</TableCell>
                <TableCell>
                  <Badge variant={config.variant}>{config.label}</Badge>
                </TableCell>
                <TableCell>{formatDate(policy.expiration_date)}</TableCell>
                <TableCell>
                  {status === 'renewal' ? (
                    <Button size="sm">Get Quotes</Button>
                  ) : (
                    <Button size="sm" variant="secondary">Review</Button>
                  )}
                </TableCell>
              </motion.tr>
            );
          })}
        </TableBody>
      </Table>
    </motion.div>
  );
}

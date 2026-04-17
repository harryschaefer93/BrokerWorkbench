import { motion } from 'framer-motion';
import { Card, CardContent, CardHeader, CardTitle, Button } from '@/components/ui';
import { useCarriers } from '@/hooks';
import { TrendingDown, Clock, CheckCircle } from 'lucide-react';
import { cn } from '@/lib/utils';

interface Quote {
  carrier_name: string;
  carrier_id: string;
  premium: number;
  current?: boolean;
  savings?: number;
  status?: 'ready' | 'pending' | 'timeout';
}

// Mock quotes for demo - in real app, this would come from API
const mockQuotes: Quote[] = [
  { carrier_name: 'State Farm', carrier_id: 'CAR001', premium: 2280, current: true, status: 'ready' },
  { carrier_name: 'Allstate', carrier_id: 'CAR002', premium: 2150, savings: 130, status: 'ready' },
  { carrier_name: 'Progressive', carrier_id: 'CAR003', premium: 2090, savings: 190, status: 'ready' },
  { carrier_name: 'Geico', carrier_id: 'CAR004', premium: 0, status: 'pending' },
];

interface CarrierQuoteCardProps {
  quote: Quote;
  index: number;
}

function CarrierQuoteCard({ quote, index }: CarrierQuoteCardProps) {
  const initials = quote.carrier_name
    .split(' ')
    .map(w => w[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
    }).format(value);
  };

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.3, delay: index * 0.1 }}
      whileHover={{ scale: 1.02, y: -2 }}
      className="cursor-pointer"
    >
      <Card className={cn(
        "text-center transition-all",
        quote.current && "ring-2 ring-primary",
        quote.savings && "ring-2 ring-emerald-500"
      )}>
        <CardContent className="p-4">
          <div className="h-11 w-11 rounded-full bg-primary text-primary-foreground flex items-center justify-center mx-auto mb-3 text-sm font-semibold">
            {initials}
          </div>
          <div className="font-semibold text-sm mb-1">{quote.carrier_name}</div>
          
          {quote.status === 'ready' ? (
            <>
              <div className={cn(
                "text-lg font-bold",
                quote.savings ? "text-blue-600" : "text-emerald-600"
              )}>
                {formatCurrency(quote.premium)}
              </div>
              <div className="text-xs text-muted-foreground mt-1">
                {quote.current ? (
                  <span className="flex items-center justify-center gap-1">
                    <CheckCircle className="h-3 w-3" /> Current Carrier
                  </span>
                ) : quote.savings ? (
                  <span className="text-emerald-600 flex items-center justify-center gap-1">
                    <TrendingDown className="h-3 w-3" /> Save {formatCurrency(quote.savings)}
                  </span>
                ) : null}
              </div>
            </>
          ) : (
            <>
              <div className="text-muted-foreground text-sm">
                {quote.status === 'pending' ? 'Quote Pending...' : 'API Timeout'}
              </div>
              <div className="text-xs text-muted-foreground mt-1 flex items-center justify-center gap-1">
                <Clock className="h-3 w-3" /> {quote.status === 'pending' ? 'Processing' : 'Retry'}
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </motion.div>
  );
}

interface CarrierQuotesProps {
  clientName?: string;
  policyType?: string;
}

export function CarrierQuotes({ clientName = 'Smith Family', policyType = 'Auto' }: CarrierQuotesProps) {
  const { data: carriers } = useCarriers();

  // Use mock quotes with carrier data
  const quotes = mockQuotes.map(q => {
    const carrier = carriers.find(c => c.carrier_id === q.carrier_id);
    return {
      ...q,
      carrier_name: carrier?.name || q.carrier_name,
    };
  });

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base flex items-center gap-2">
          Real-Time Carrier Quotes - {clientName} {policyType}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
          {quotes.map((quote, index) => (
            <CarrierQuoteCard key={quote.carrier_id} quote={quote} index={index} />
          ))}
        </div>
        
        <div className="flex flex-wrap gap-2">
          <Button>Present Quotes to Client</Button>
          <Button variant="secondary">Schedule Call</Button>
          <Button variant="secondary">Send Email Summary</Button>
        </div>
      </CardContent>
    </Card>
  );
}

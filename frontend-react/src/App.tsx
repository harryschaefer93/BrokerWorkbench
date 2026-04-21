import { useState } from 'react';
import { Header, Sidebar } from '@/components/layout';
import { 
  PolicyTable, 
  CarrierQuotes, 
  CrossSellOpportunities,
  DocumentManagement,
  QuickFilters,
} from '@/components/dashboard';
import { AIChatPanel, SmartInsights } from '@/components/chat';
import { 
  RenewalTrendChart, 
  PolicyDistributionChart,
} from '@/components/charts';
import { Card, CardHeader, CardTitle, CardContent, ScrollArea } from '@/components/ui';
import { FileText } from 'lucide-react';
import { motion } from 'framer-motion';

function App() {
  const [activeFilter, setActiveFilter] = useState<string>();

  return (
    <div className="min-h-screen bg-background">
      <Header urgentCount={3} />
      
      <div className="flex">
        {/* Left Sidebar */}
        <Sidebar />
        
        {/* Main Content */}
        <main className="flex-1 h-[calc(100vh-4rem)] overflow-y-auto">
          <ScrollArea className="h-full">
            <div className="p-6 space-y-6">
              {/* Page Header */}
              <motion.div
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3 }}
              >
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h1 className="text-2xl font-bold">Policy Management & Market Intelligence</h1>
                    <p className="text-muted-foreground text-sm mt-1">
                      Manage your book of business with AI-powered insights
                      <span className="inline-flex items-center gap-1 ml-2 text-xs text-violet-500 font-medium">
                        <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                          <path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z" fill="currentColor"/>
                        </svg>
                        Microsoft Foundry
                      </span>
                    </p>
                  </div>
                </div>
                
                {/* Quick Filters */}
                <QuickFilters 
                  activeFilter={activeFilter}
                  onFilterClick={setActiveFilter}
                />
              </motion.div>

              {/* Policy Table */}
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base flex items-center gap-2">
                    <FileText className="h-4 w-4" />
                    Active Policies
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <PolicyTable />
                </CardContent>
              </Card>

              {/* Carrier Quotes + Cross-sell Grid */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2">
                  <CarrierQuotes />
                </div>
                <div>
                  <CrossSellOpportunities />
                </div>
              </div>

              {/* Charts Row */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <RenewalTrendChart />
                <PolicyDistributionChart />
              </div>

              {/* Document Management */}
              <DocumentManagement />

              {/* Smart Insights (visible on smaller screens when chat panel is hidden) */}
              <div className="lg:hidden">
                <SmartInsights />
              </div>
            </div>
          </ScrollArea>
        </main>

        {/* Right AI Chat Panel */}
        <AIChatPanel />
      </div>
    </div>
  );
}

export default App;

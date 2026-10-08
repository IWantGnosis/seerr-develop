import Button from '@app/components/Common/Button';
import Header from '@app/components/Common/Header';
import LoadingSpinner from '@app/components/Common/LoadingSpinner';
import PageTitle from '@app/components/Common/PageTitle';
import DownloadJobCard from '@app/components/Downloads/DownloadJobCard';
import {
  cancelDownloadJob,
  deleteDownloadJob,
  getDownloadJobs,
  getScraperLogs,
  type DownloadJob,
  type DownloadStatus,
} from '@app/components/Downloads/downloadService';
import {
  ArrowPathIcon,
  CommandLineIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline';
import { useEffect, useRef, useState } from 'react';
import useSWR from 'swr';

type DownloadFilter =
  | 'ALL'
  | 'DOWNLOADING'
  | 'QUEUED'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED';
const filters: { label: string; value: DownloadFilter }[] = [
  { label: 'All', value: 'ALL' },
  { label: 'Downloading', value: 'DOWNLOADING' },
  { label: 'Queued', value: 'QUEUED' },
  { label: 'Completed', value: 'COMPLETED' },
  { label: 'Failed', value: 'FAILED' },
  { label: 'Cancelled', value: 'CANCELLED' },
];
const matchesFilter = (job: DownloadJob, filter: DownloadFilter) =>
  filter === 'ALL' ||
  (filter === 'DOWNLOADING'
    ? ['SEARCHING', 'FOUND', 'DOWNLOADING'].includes(job.status)
    : job.status === (filter as DownloadStatus));

const Downloads = () => {
  const [filter, setFilter] = useState<DownloadFilter>('ALL');
  const [showLogs, setShowLogs] = useState(false);
  const logEndRef = useRef<HTMLDivElement>(null);

  const {
    data: jobs,
    error,
    mutate,
  } = useSWR('downloads/jobs', getDownloadJobs, {
    refreshInterval: (latestData) => {
      const hasActive = latestData?.some((j) =>
        ['QUEUED', 'SEARCHING', 'FOUND', 'DOWNLOADING'].includes(j.status)
      );
      // Poll every 2.5s while active, stop polling (0) once all jobs are completed/failed
      return hasActive ? 2500 : 0;
    },
    revalidateOnFocus: true,
  });

  const handleCancelJob = async (jobId: string) => {
    await cancelDownloadJob(jobId);
    await mutate();
  };

  const handleDeleteJob = async (jobId: string) => {
    await deleteDownloadJob(jobId);
    await mutate();
  };

  const { data: logs } = useSWR(
    showLogs ? 'downloads/scraper-logs' : null,
    getScraperLogs,
    {
      refreshInterval: 2000,
    }
  );

  useEffect(() => {
    if (showLogs && logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs, showLogs]);

  const filteredJobs = jobs?.filter((job) => matchesFilter(job, filter)) ?? [];
  return (
    <>
      <PageTitle title="Downloads" />
      <div className="mb-4 flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
        <Header>Downloads</Header>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setShowLogs(!showLogs)}
            className={`inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition focus:outline-none focus:ring-2 focus:ring-emerald-500 ${
              showLogs
                ? 'bg-emerald-600 text-white shadow-lg shadow-emerald-900/30'
                : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
            }`}
          >
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500"></span>
            </span>
            <CommandLineIcon className="h-4 w-4" />
            <span>{showLogs ? 'Hide Scraper Logs' : 'View Scraper Logs'}</span>
          </button>

          <div
            className="flex gap-2 overflow-x-auto pb-1"
            role="tablist"
            aria-label="Download status filters"
          >
            {filters.map((item) => (
              <button
                key={item.value}
                className={`whitespace-nowrap rounded-md px-3 py-2 text-sm font-medium transition focus:outline-none focus:ring-2 focus:ring-indigo-500 ${
                  filter === item.value
                    ? 'bg-indigo-600 text-white'
                    : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
                }`}
                type="button"
                role="tab"
                aria-selected={filter === item.value}
                onClick={() => setFilter(item.value)}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {showLogs && (
        <div className="mb-6 overflow-hidden rounded-xl border border-gray-800 bg-gray-950 p-4 shadow-2xl">
          <div className="mb-3 flex items-center justify-between border-b border-gray-800/80 pb-2">
            <div className="flex items-center gap-2 text-xs font-semibold tracking-wider text-emerald-400 uppercase">
              <CommandLineIcon className="h-4 w-4" />
              <span>Scraper Live Activity Stream</span>
            </div>
            <span className="text-xs text-gray-500">Auto-refresh (2s)</span>
          </div>
          <div className="max-h-72 overflow-y-auto font-mono text-xs text-gray-300 space-y-1 pr-2">
            {logs && logs.length > 0 ? (
              logs.map((log, i) => (
                <div key={i} className="whitespace-pre-wrap leading-relaxed">
                  <span className="text-emerald-500/80">&gt;</span> {log}
                </div>
              ))
            ) : (
              <div className="py-6 text-center text-gray-500 italic">
                No active scraper activity recorded yet. When a movie request is approved, real-time bypass and download activity will stream here.
              </div>
            )}
            <div ref={logEndRef} />
          </div>
        </div>
      )}
      {!jobs && !error && <LoadingSpinner />}
      {error && (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <ExclamationTriangleIcon className="h-12 w-12 text-red-400" />
          <p className="mt-4 text-lg text-gray-200">
            Unable to load downloads.
          </p>
          <Button
            className="mt-4"
            buttonType="primary"
            onClick={() => mutate()}
          >
            <ArrowPathIcon />
            <span>Try Again</span>
          </Button>
        </div>
      )}
      {jobs && !error && filteredJobs.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <div className="rounded-full bg-gray-800/80 p-4 text-indigo-400">
            <CommandLineIcon className="h-10 w-10" />
          </div>
          <p className="mt-4 text-xl font-medium text-gray-200">No active downloads</p>
          <p className="mt-1 max-w-md text-sm text-gray-400">
            When you request a movie, it will be automatically scraped and saved directly into your Jellyfin library (<span className="font-mono text-indigo-300">Hollywood Movies</span> or <span className="font-mono text-indigo-300">Bollywood Movies</span>).
          </p>
          {filter !== 'ALL' && (
            <Button
              className="mt-4"
              buttonType="primary"
              onClick={() => setFilter('ALL')}
            >
              Show All Downloads
            </Button>
          )}
        </div>
      )}
      {jobs && !error && filteredJobs.length > 0 && (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {filteredJobs.map((job) => (
            <DownloadJobCard
              key={job.id}
              job={job}
              onCancel={handleCancelJob}
              onDelete={handleDeleteJob}
            />
          ))}
        </div>
      )}
    </>
  );
};
export default Downloads;

module.exports = {
  style: 'elastic-web',
  name: 'claude-code-transcripts-load-test',
  title: 'Claude Code Transcripts: Load Test',
  port: 30001,

  slides: [
    '01-cover.html',
    '02-method.html',
    '03-embedding.html',
    '04-saturation.html',
    '05-autoscaling.html',
    '06-fixed.html',
    '07-cache.html',
    '08-sizing.html',
    '09-levers.html',
    '10-lessons.html',
    '11-closing.html',
  ],

  labels: [
    'Cover',
    'Method',
    'Phase 1: Embedding only',
    'Phase 2: Saturation',
    'Why it did not scale',
    'Phase 3: Fixed allocations',
    'Inference cache',
    'Sizing for 25k/h',
    'Throughput levers',
    'Field notes',
    'Takeaway',
  ],
};

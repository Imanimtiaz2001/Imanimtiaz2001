import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import App from '../src/App';

const config = {
  provider: 'openai',
  ready: true,
  voices: ['coral'],
  languages: ['auto', 'en', 'ur'],
  max_audio_seconds: 60,
  max_audio_bytes: 10485760,
  setup_hint: 'Set OPENAI_API_KEY on the server.',
};
const turn = {
  id: 't1',
  request_id: 'r1',
  transcript: 'Hello',
  answer: { text: 'A clear answer.', sources: [], abstained: false },
  audio_url: null,
  warning: 'Speech failed.',
  mode: 'general',
  timings: { total_ms: 1000 },
  created_at: '2026-10-01',
};
function mockFetch(options: { ready?: boolean; fail?: boolean } = {}) {
  const calls: { path: string; init?: RequestInit }[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (path: string, init?: RequestInit) => {
      calls.push({ path, init });
      let data: unknown = [];
      let status = 200;
      if (path === '/api/config') data = { ...config, ready: options.ready ?? true };
      else if (path === '/api/conversations' && init?.method === 'POST')
        data = { id: 'c1', title: 'New conversation' };
      else if (path.endsWith('/turns')) {
        if (options.fail) {
          status = 503;
          data = { error: { code: 'provider_unavailable', message: 'Provider is unavailable.' } };
        } else data = turn;
      } else if (path === '/api/conversations/c1') data = { turns: [turn] };
      else if (path === '/api/documents' && init?.method === 'POST')
        data = { id: 'd1', name: 'note.md' };
      return { ok: status < 400, status, json: async () => data };
    }),
  );
  return calls;
}

describe('VoxDesk', () => {
  it('sends a question and displays answer, recovery and timing controls', async () => {
    const calls = mockFetch();
    render(<App />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Your question'), 'Hello');
    await waitFor(() => expect(screen.getByLabelText('Send question')).not.toBeDisabled());
    await user.click(screen.getByLabelText('Send question'));
    expect(await screen.findByText('A clear answer.')).toBeInTheDocument();
    expect(screen.getByText('Retry voice')).toBeInTheDocument();
    expect(screen.getByLabelText('Your question')).toHaveValue('');
    const submission = calls.find((call) => call.path.endsWith('/turns'))?.init?.body as FormData;
    expect(submission.get('text')).toBe('Hello');
    expect(submission.get('mode')).toBe('general');
  });
  it('keeps the question and offers retry after a provider error', async () => {
    mockFetch({ fail: true });
    render(<App />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Your question'), 'Hello');
    await waitFor(() => expect(screen.getByLabelText('Send question')).not.toBeDisabled());
    await user.click(screen.getByLabelText('Send question'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Provider is unavailable.');
    expect(screen.getByLabelText('Your question')).toHaveValue('Hello');
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });
  it('opens settings, uploads notes and selects knowledge mode', async () => {
    const calls = mockFetch();
    render(<App />);
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByText('Ready to listen')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: 'Knowledge & settings' }));
    const file = new File(['PostgreSQL uses transactions.'], 'note.md', { type: 'text/markdown' });
    fireEvent.change(screen.getByLabelText('Note file'), { target: { files: [file] } });
    await waitFor(() =>
      expect(
        calls.some((call) => call.path === '/api/documents' && call.init?.method === 'POST'),
      ).toBe(true),
    );
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /My notes/ })).toHaveClass('active'),
    );
  });
  it('shows provider setup instructions instead of pretending to run AI', async () => {
    mockFetch({ ready: false });
    render(<App />);
    expect(await screen.findByText('Your voice provider needs setup.')).toBeInTheDocument();
    expect(screen.getByText(/Set OPENAI_API_KEY/)).toBeInTheDocument();
  });
  it('fills suggestions without making a model call', async () => {
    const calls = mockFetch();
    render(<App />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /Understand an idea/ }));
    expect(screen.getByLabelText('Your question')).toHaveValue(
      'Why would I choose PostgreSQL over MongoDB?',
    );
    expect(calls.some((call) => call.path.endsWith('/turns'))).toBe(false);
  });
});

it('copies an imperfect transcript into the composer for correction', async () => {
  mockFetch();
  render(<App />);
  const user = userEvent.setup();
  await user.type(screen.getByLabelText('Your question'), 'Hello');
  await waitFor(() => expect(screen.getByLabelText('Send question')).not.toBeDisabled());
  await user.click(screen.getByLabelText('Send question'));
  await user.click(await screen.findByRole('button', { name: 'Edit question' }));
  expect(screen.getByLabelText('Your question')).toHaveValue('Hello');
});

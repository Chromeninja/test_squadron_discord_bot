import { useMemo, useState } from 'react';
import { authApi, type UserProfile } from '../api/endpoints';
import AccordionSection from '../components/AccordionSection';
import { Button, Card } from '../components/ui';
import { handleApiError } from '../utils/toast';

interface LandingProps {
  loginHref: string;
  user: UserProfile | null;
  dashboardHref?: string;
}

interface FeatureItem {
  title: string;
  body: string;
  icon: string;
}

interface FaqItem {
  question: string;
  answer: string;
}

const FEATURES: FeatureItem[] = [
  {
    title: 'RSI Verification Workflow',
    body: 'Guide members through profile verification, keep role assignment consistent, and reduce manual review overhead.',
    icon: '🛡️',
  },
  {
    title: 'Voice Channel Management',
    body: 'Automate temporary voice spaces, ownership controls, and moderation-safe defaults for active squad operations.',
    icon: '🎧',
  },
  {
    title: 'Role and Access Governance',
    body: 'Apply structured role policies for bot admins, moderators, and staff with clear permission boundaries.',
    icon: '🔐',
  },
  {
    title: 'Operational Metrics',
    body: 'Track activity trends, voice engagement, and participation health with dashboard-ready insights.',
    icon: '📈',
  },
  {
    title: 'Ticketing and Member Support',
    body: 'Provide scalable intake and resolution flows for support, onboarding, and recurring community requests.',
    icon: '🎫',
  },
  {
    title: 'Guild-Level Configuration',
    body: 'Configure channels, notifications, and module behavior per server without breaking central governance.',
    icon: '⚙️',
  },
];

const FAQ_ITEMS: FaqItem[] = [
  {
    question: 'What is this bot designed for?',
    answer:
      'The TEST Squadron bot is built for Star Citizen community operations: verification, role management, voice workflows, events, and support tooling in one place.',
  },
  {
    question: 'Who can configure critical settings?',
    answer:
      'Configuration is role-gated. Bot admins and approved staff can manage sensitive settings based on the permission model applied to each guild.',
  },
  {
    question: 'Can any logged-in user add the bot to a server?',
    answer:
      'No. The Add Bot action is restricted to bot admins only. If you need the bot in your server, contact chromeninja@test.gg.',
  },
  {
    question: 'Do I need to verify before using member features?',
    answer:
      'Verification requirements are configurable per guild, but verification is typically used to unlock trusted access and reduce abuse risk.',
  },
  {
    question: 'Is this page the dashboard?',
    answer:
      'This is the public info and knowledge base landing page. After login, authorized users are routed to the management dashboard for their server context.',
  },
  {
    question: 'How do I request onboarding help?',
    answer:
      'Send your server details and use case to chromeninja@test.gg. You can also include expected member count and which modules you want enabled first.',
  },
];

function LockedBadge({ text }: { text: string }) {
  return (
    <span className="inline-flex items-center rounded-full border border-[#ffbb00]/35 bg-[#ffbb00]/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.08em] text-[#ffe8a6]">
      {text}
    </span>
  );
}

export default function Landing({ loginHref, user, dashboardHref }: LandingProps) {
  const [isInviting, setIsInviting] = useState(false);

  const isLoggedIn = user !== null;
  const isBotAdmin = user?.is_bot_owner === true;
  const showAddBotControls = isLoggedIn;
  const addBotDisabled = !isBotAdmin || isInviting;
  const primaryCtaHref = user ? dashboardHref ?? '/select-server' : loginHref;
  const primaryCtaLabel = user ? 'Open Dashboard' : 'Login with Discord';

  const addBotHelperText = useMemo(() => {
    if (isBotAdmin) {
      return 'Bot Admin access detected. You can start the Discord invite flow.';
    }

    if (!user) {
      return 'Locked: login required and bot admin permission is required.';
    }

    return 'Locked: only bot admins can add the bot to servers.';
  }, [isBotAdmin, user]);

  const handleAddBot = async (): Promise<void> => {
    if (!isBotAdmin) {
      return;
    }

    setIsInviting(true);
    try {
      const response = await authApi.getBotInviteUrl();
      window.location.assign(response.invite_url);
    } catch (error: unknown) {
      handleApiError(error, 'Failed to start bot invite flow');
      setIsInviting(false);
    }
  };

  return (
    <div className="dashboard-theme min-h-screen text-[#f5deb3]">
      <div className="relative overflow-hidden border-b border-[#ffbb00]/15">
        <div className="pointer-events-none absolute -top-28 left-1/2 h-[26rem] w-[26rem] -translate-x-1/2 rounded-full bg-[radial-gradient(circle,rgba(255,187,0,0.16),rgba(255,187,0,0.02)_42%,transparent_70%)]" />

        <section className="relative mx-auto max-w-6xl px-4 pb-20 pt-14 sm:pt-20">
          <div className="mb-8 flex items-center justify-between gap-3">
            <div className="text-xs uppercase tracking-[0.22em] text-[#ffdd73]">TEST Squadron Bot</div>
            {showAddBotControls && !isBotAdmin && <LockedBadge text="Add Bot: Bot Admin Only" />}
          </div>

          <div className="grid gap-12 lg:grid-cols-[1.05fr_0.95fr] lg:items-center">
            <div>
              <h1 className="dashboard-title text-4xl font-bold leading-tight sm:text-5xl lg:text-6xl">
                Community Operations,
                <span className="block text-[#ffdd73]">Mission-Ready From Day One</span>
              </h1>
              <p className="mt-6 max-w-2xl text-base leading-7 text-[#d6c7a3] sm:text-lg">
                A single operational hub for verification, voice management, moderation workflows, and member support. Built to keep your Discord server consistent, secure, and easier to run.
              </p>

              <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                <a href={primaryCtaHref} className="sm:min-w-[220px]">
                  <Button className="w-full" size="lg">
                    {primaryCtaLabel}
                  </Button>
                </a>
                {showAddBotControls && (
                  <Button
                    className="sm:min-w-[220px]"
                    variant="success"
                    size="lg"
                    onClick={() => void handleAddBot()}
                    disabled={addBotDisabled}
                    loading={isInviting}
                    title={addBotDisabled ? 'Bot admin permission required' : 'Add bot to a Discord server'}
                  >
                    Add Bot to Server
                  </Button>
                )}
              </div>

              {showAddBotControls && <p className="mt-3 text-sm text-[#a89465]">{addBotHelperText}</p>}

              <div className="mt-8 rounded-xl border border-[#ffbb00]/20 bg-[linear-gradient(180deg,rgba(255,187,0,0.1),rgba(255,187,0,0.03))] p-4 sm:p-5">
                <p className="text-sm font-semibold uppercase tracking-[0.1em] text-[#ffe8a6]">Need the bot in your server?</p>
                <p className="mt-2 text-sm text-[#d6c7a3]">
                  Reach out at{' '}
                  <a
                    href="mailto:chromeninja@test.gg"
                    className="font-semibold text-[#ffdd73] underline decoration-[#ffbb00]/55 underline-offset-4"
                  >
                    chromeninja@test.gg
                  </a>
                  {' '}for onboarding and deployment support.
                </p>
              </div>
            </div>

            <Card
              className="dashboard-panel border-[#ffbb00]/28 bg-[linear-gradient(170deg,rgba(17,13,7,0.92),rgba(11,9,5,0.96))]"
              padding="lg"
            >
              <p className="text-xs uppercase tracking-[0.14em] text-[#ffdd73]">At a glance</p>
              <h2 className="mt-3 text-2xl font-semibold text-[#fff1bf]">What you get</h2>
              <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div className="rounded-lg border border-[#ffbb00]/18 bg-[#0f1014] p-4">
                  <p className="text-xs uppercase tracking-[0.08em] text-[#a89465]">Security posture</p>
                  <p className="mt-1 text-lg font-semibold text-[#fff4cc]">Role-gated controls</p>
                </div>
                <div className="rounded-lg border border-[#ffbb00]/18 bg-[#0f1014] p-4">
                  <p className="text-xs uppercase tracking-[0.08em] text-[#a89465]">Operations</p>
                  <p className="mt-1 text-lg font-semibold text-[#fff4cc]">Verification + Voice</p>
                </div>
                <div className="rounded-lg border border-[#ffbb00]/18 bg-[#0f1014] p-4">
                  <p className="text-xs uppercase tracking-[0.08em] text-[#a89465]">Governance</p>
                  <p className="mt-1 text-lg font-semibold text-[#fff4cc]">Scoped admin roles</p>
                </div>
                <div className="rounded-lg border border-[#ffbb00]/18 bg-[#0f1014] p-4">
                  <p className="text-xs uppercase tracking-[0.08em] text-[#a89465]">Support</p>
                  <p className="mt-1 text-lg font-semibold text-[#fff4cc]">Ticket workflow</p>
                </div>
              </div>
            </Card>
          </div>
        </section>
      </div>

      <section className="mx-auto max-w-6xl px-4 py-16 sm:py-20">
        <div className="mb-8 flex flex-col gap-2">
          <h2 className="dashboard-section-title text-2xl font-semibold sm:text-3xl">Core capabilities</h2>
          <p className="max-w-3xl text-sm text-[#a89465] sm:text-base">
            Purpose-built modules for community reliability, role governance, and day-to-day moderation throughput.
          </p>
        </div>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {FEATURES.map((feature) => (
            <Card key={feature.title} className="dashboard-panel" hoverable padding="lg">
              <div className="text-2xl" aria-hidden="true">
                {feature.icon}
              </div>
              <h3 className="mt-3 text-lg font-semibold text-[#fff4cc]">{feature.title}</h3>
              <p className="mt-2 text-sm leading-6 text-[#c9b789]">{feature.body}</p>
            </Card>
          ))}
        </div>
      </section>

      <section className="border-y border-[#ffbb00]/14 bg-[linear-gradient(180deg,rgba(14,11,6,0.74),rgba(10,8,5,0.86))]">
        <div className="mx-auto max-w-4xl px-4 py-16 sm:py-20">
          <div className="mb-7">
            <h2 className="dashboard-section-title text-2xl font-semibold sm:text-3xl">Knowledge base FAQ</h2>
            <p className="mt-2 text-sm text-[#a89465] sm:text-base">
              Quick answers before login, so admins and staff understand the operating model up front.
            </p>
          </div>
          <div className="space-y-4">
            {FAQ_ITEMS.map((item, index) => (
              <AccordionSection
                key={item.question}
                title={item.question}
                defaultOpen={index === 0}
              >
                <p className="text-sm leading-6 text-[#d6c7a3]">{item.answer}</p>
              </AccordionSection>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-5xl px-4 py-14 sm:py-18">
        <Card
          className="dashboard-panel border-[#ffbb00]/28 bg-[linear-gradient(150deg,rgba(255,187,0,0.12),rgba(255,187,0,0.03))]"
          padding="lg"
        >
          <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-2xl font-bold text-[#fff1bf]">Ready to continue?</h2>
              <p className="mt-2 max-w-2xl text-sm text-[#d6c7a3] sm:text-base">
                Login to access your guild dashboard, or contact chromeninja@test.gg if you need the bot deployed to a new community.
              </p>
            </div>
            <div className="flex min-w-[220px] flex-col gap-3">
              <a href={primaryCtaHref}>
                <Button className="w-full" size="lg">
                  {primaryCtaLabel}
                </Button>
              </a>
              {showAddBotControls && (
                <Button
                  variant="secondary"
                  size="lg"
                  onClick={() => void handleAddBot()}
                  disabled={addBotDisabled}
                >
                  Add Bot to Server
                </Button>
              )}
            </div>
          </div>
        </Card>
      </section>
    </div>
  );
}

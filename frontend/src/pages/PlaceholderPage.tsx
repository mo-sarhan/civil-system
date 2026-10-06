/** Honest placeholder for sections that are still being built out. */
export default function PlaceholderPage({ title }: { title: string }) {
  return (
    <div>
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">{title}</h1>
      </header>
      <div className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center text-sm text-slate-500">
        هذه الشاشة قيد الإنشاء ولم تُربط بعد بواجهات API.
      </div>
    </div>
  );
}

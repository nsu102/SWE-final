"use client";

export default function MemberGate({ title, text, onLogin }: {
  title: string;
  text: string;
  onLogin: () => void;
}) {
  return <section className="member-gate">
    <h1>{title}</h1>
    <p>{text}</p>
    <button className="photo-action" onClick={onLogin}>LOGIN <span aria-hidden="true">↗</span></button>
  </section>;
}

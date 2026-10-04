"use client";

import { CSSProperties, useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  CARD_FLIP_DURATION, CARD_STAGGER, FILTER_COLLAPSE_DELAY, FILTER_SWAP_DELAY, FILTER_SWAP_SETTLE,
  GRID_SCROLL_RESET, PLATFORM_FILTERS,
} from "../constants/look-find";
import type { Product } from "../types/api";
import { productKey } from "../utils/product";

export type FilterCard = { item: Product; key: string; className: string; style?: CSSProperties; ref: (element: HTMLElement | null) => void };

/**
 * Platform filter for the results grid, with its card motion:
 * - ALL ↔ platform: cards that leave fade out, the rest FLIP into their new slots
 * - platform ↔ platform: slots flip in place, extra cards float in / depart
 */
export function usePlatformFilter(matches: Product[]) {
  const [filter, setFilter] = useState("all");
  const [displayedFilter, setDisplayedFilter] = useState("all");
  const [pendingFilter, setPendingFilter] = useState<string | null>(null);
  const [isSourceSwap, setIsSourceSwap] = useState(false);
  const [swapPreviousCount, setSwapPreviousCount] = useState(0);
  const [departingCards, setDepartingCards] = useState<Product[]>([]);
  const [headingVisible, setHeadingVisible] = useState(true);
  const cardRefs = useRef(new Map<string, HTMLElement>());
  const previousCardPositions = useRef(new Map<string, DOMRect>());
  const filterTimer = useRef<number | null>(null);
  const scrollResetFrame = useRef<number | null>(null);
  const matchGridRef = useRef<HTMLDivElement>(null);
  const byPlatform = (id: string) => matches.filter(item => id === "all" || item.platform === id);
  const visibleMatches = byPlatform(displayedFilter);
  const displayMatches = isSourceSwap && !pendingFilter ? [...visibleMatches, ...departingCards] : visibleMatches;

  useEffect(() => () => {
    if (filterTimer.current) window.clearTimeout(filterTimer.current);
    if (scrollResetFrame.current) window.cancelAnimationFrame(scrollResetFrame.current);
  }, []);

  // FLIP: animate each remaining card from where it was before the filter changed.
  useLayoutEffect(() => {
    if (!previousCardPositions.current.size) return;
    cardRefs.current.forEach((card, id) => {
      const previous = previousCardPositions.current.get(id);
      if (!previous) return;
      const next = card.getBoundingClientRect();
      const x = previous.left - next.left;
      const y = previous.top - next.top;
      if (x || y) card.animate([{ transform: `translate(${x}px, ${y}px)` }, { transform: "translate(0, 0)" }], { duration: CARD_FLIP_DURATION, easing: "cubic-bezier(.2, .8, .25, 1)" });
    });
    previousCardPositions.current.clear();
  }, [displayedFilter]);

  function scrollGridToTop() {
    const grid = matchGridRef.current;
    if (!grid || grid.scrollTop <= 0) return;
    if (scrollResetFrame.current) window.cancelAnimationFrame(scrollResetFrame.current);
    const start = grid.scrollTop;
    let startedAt: number | null = null;
    const step = (now: number) => {
      startedAt ??= now;
      const progress = Math.min((now - startedAt) / GRID_SCROLL_RESET, 1);
      grid.scrollTop = start * (1 - (1 - (1 - progress) ** 3));
      if (progress < 1) scrollResetFrame.current = window.requestAnimationFrame(step);
    };
    scrollResetFrame.current = window.requestAnimationFrame(step);
  }

  function changeFilter(nextFilter: string) {
    if (nextFilter === filter || pendingFilter || isSourceSwap) return;
    const sourceSwap = displayedFilter !== "all" && nextFilter !== "all";
    const nextMatches = byPlatform(nextFilter);
    cardRefs.current.forEach((card, id) => previousCardPositions.current.set(id, card.getBoundingClientRect()));
    if (sourceSwap) {
      setSwapPreviousCount(visibleMatches.length);
      setDepartingCards(nextMatches.length < visibleMatches.length ? visibleMatches.slice(nextMatches.length) : []);
    } else setDepartingCards([]);
    scrollGridToTop();
    setIsSourceSwap(sourceSwap);
    setPendingFilter(nextFilter);
    setFilter(nextFilter);
    filterTimer.current = window.setTimeout(() => {
      setDisplayedFilter(nextFilter);
      setPendingFilter(null);
      if (sourceSwap) window.setTimeout(() => { setIsSourceSwap(false); setDepartingCards([]); }, FILTER_SWAP_SETTLE);
    }, sourceSwap ? FILTER_SWAP_DELAY : FILTER_COLLAPSE_DELAY);
  }

  const pendingMatchCount = pendingFilter ? byPlatform(pendingFilter).length : visibleMatches.length;
  const cards: FilterCard[] = displayMatches.map((item, index) => {
    const id = productKey(item);
    const leaving = !isSourceSwap && Boolean(pendingFilter && pendingFilter !== "all" && item.platform !== pendingFilter);
    const departing = isSourceSwap && index >= (pendingFilter ? pendingMatchCount : visibleMatches.length);
    const floating = isSourceSwap && !pendingFilter && index >= swapPreviousCount;
    const flipping = isSourceSwap && !floating && !departing;
    return {
      item,
      key: isSourceSwap ? `swap-slot-${index}` : id,
      className: ["match-card", leaving && "leaving", flipping && "source-flipping", floating && "source-floating", departing && "source-departing"].filter(Boolean).join(" "),
      style: floating ? { animationDelay: `${(index - swapPreviousCount) * CARD_STAGGER}ms` } : undefined,
      ref: element => { if (element) cardRefs.current.set(id, element); else cardRefs.current.delete(id); },
    };
  });

  return {
    filter, activeIndex: PLATFORM_FILTERS.findIndex(({ id }) => id === filter), changeFilter, cards, matchGridRef,
    headingVisible, onGridScroll: (top: number) => setHeadingVisible(top < 2),
  };
}

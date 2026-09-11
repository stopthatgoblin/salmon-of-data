import { test } from 'node:test';
import assert from 'node:assert/strict';
import { niceScale } from '../lib/axis.ts';
test('whole-dollar axes retain range and do not manufacture decimal labels',()=>{const {ticks,domain}=niceScale([150.3,278.6]);assert.ok(ticks.every(Number.isInteger));assert.ok(domain[0]<=150.3&&domain[1]>=278.6);});
test('sub-dollar sugar prices have distinct whole-cent ticks',()=>{const {ticks}=niceScale([.21,.551],.05);assert.ok(ticks.every(v=>Math.abs(v*100-Math.round(v*100))<1e-8));assert.equal(new Set(ticks.map(v=>Math.round(v*100))).size,ticks.length);});

test('narrow whole-unit axes also use exact integer tick positions',()=>{assert.ok(niceScale([10.3,19.1]).ticks.every(Number.isInteger));});

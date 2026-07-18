"use client";

import { useEffect, useRef } from "react";

export type OrbitalPointer = {
  x: number;
  y: number;
};

type OrbitalWorldProps = {
  activeScene: number;
  pointerRef: { current: OrbitalPointer };
  reducedMotion: boolean;
};

const sceneTargets = [
  {
    accent: 0xffb84d,
    beaconOpacity: 0.18,
    camera: [0.8, 0.4, 8.2],
    coreScale: 0.78,
    orbitOpacity: 0.22,
    position: [2.6, -0.25, 0],
    rotation: [-0.16, -0.48, 0.08],
  },
  {
    accent: 0x62c8ff,
    beaconOpacity: 0.28,
    camera: [-0.5, 1.25, 10.4],
    coreScale: 0.62,
    orbitOpacity: 0.4,
    position: [0.3, -0.35, -0.7],
    rotation: [0.12, 0.3, -0.22],
  },
  {
    accent: 0x62c8ff,
    beaconOpacity: 0.9,
    camera: [1.8, 0.15, 9.5],
    coreScale: 0.9,
    orbitOpacity: 0.3,
    position: [-2.45, 0.1, -0.35],
    rotation: [-0.04, 0.9, 0.18],
  },
  {
    accent: 0xff755f,
    beaconOpacity: 0.42,
    camera: [-0.3, -0.1, 7.5],
    coreScale: 1.2,
    orbitOpacity: 0.48,
    position: [-2.2, 0.35, 0.2],
    rotation: [0.22, 1.45, -0.12],
  },
] as const;

function seededRandom(seed: number) {
  let value = seed >>> 0;
  return () => {
    value = (value * 1664525 + 1013904223) >>> 0;
    return value / 4294967296;
  };
}

export function OrbitalWorld({ activeScene, pointerRef, reducedMotion }: OrbitalWorldProps) {
  const activeSceneRef = useRef(activeScene);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const reducedMotionRef = useRef(reducedMotion);
  const renderStaticRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    activeSceneRef.current = activeScene;
    renderStaticRef.current?.();
  }, [activeScene]);

  useEffect(() => {
    reducedMotionRef.current = reducedMotion;
    renderStaticRef.current?.();
  }, [reducedMotion]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    let animationFrame = 0;
    let disposed = false;
    let lastFrame = window.performance.now();
    let teardownRuntime: (() => void) | undefined;

    const initialize = async () => {
      try {
        const THREE = await import("three");
        if (disposed) return;

        const isCompact = window.matchMedia("(max-width: 768px)").matches;
        const renderer = new THREE.WebGLRenderer({
          alpha: true,
          antialias: !isCompact,
          canvas,
          powerPreference: "high-performance",
        });
        renderer.outputColorSpace = THREE.SRGBColorSpace;
        renderer.setClearColor(0x030609, 0);

        const scene = new THREE.Scene();
        scene.fog = new THREE.FogExp2(0x05090d, 0.035);

        const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 90);
        camera.position.set(...sceneTargets[0].camera);

        const world = new THREE.Group();
        scene.add(world);

        const random = seededRandom(8172026);
        const starCount = isCompact ? 420 : 920;
        const starPositions = new Float32Array(starCount * 3);
        const starColors = new Float32Array(starCount * 3);
        const cool = new THREE.Color(0x62c8ff);
        const warm = new THREE.Color(0xffd49a);
        for (let index = 0; index < starCount; index += 1) {
          const radius = 12 + random() * 35;
          const theta = random() * Math.PI * 2;
          const phi = Math.acos(2 * random() - 1);
          starPositions[index * 3] = radius * Math.sin(phi) * Math.cos(theta);
          starPositions[index * 3 + 1] = radius * Math.cos(phi) * 0.72;
          starPositions[index * 3 + 2] = radius * Math.sin(phi) * Math.sin(theta) - 8;
          const color = random() > 0.74 ? warm : cool;
          const intensity = 0.45 + random() * 0.55;
          starColors[index * 3] = color.r * intensity;
          starColors[index * 3 + 1] = color.g * intensity;
          starColors[index * 3 + 2] = color.b * intensity;
        }
        const starGeometry = new THREE.BufferGeometry();
        starGeometry.setAttribute("position", new THREE.BufferAttribute(starPositions, 3));
        starGeometry.setAttribute("color", new THREE.BufferAttribute(starColors, 3));
        const starMaterial = new THREE.PointsMaterial({
          blending: THREE.AdditiveBlending,
          depthWrite: false,
          opacity: 0.72,
          size: isCompact ? 0.035 : 0.048,
          sizeAttenuation: true,
          transparent: true,
          vertexColors: true,
        });
        const stars = new THREE.Points(starGeometry, starMaterial);
        scene.add(stars);

        const planetGeometry = new THREE.IcosahedronGeometry(1.52, isCompact ? 3 : 5);
        const planetMaterial = new THREE.MeshStandardMaterial({
          color: 0x101a22,
          emissive: 0x07131c,
          emissiveIntensity: 0.75,
          metalness: 0.28,
          roughness: 0.86,
        });
        const planet = new THREE.Mesh(planetGeometry, planetMaterial);
        world.add(planet);

        const gridMaterial = new THREE.MeshBasicMaterial({
          blending: THREE.AdditiveBlending,
          color: 0x62c8ff,
          opacity: 0.12,
          transparent: true,
          wireframe: true,
        });
        const planetGrid = new THREE.Mesh(
          new THREE.IcosahedronGeometry(1.57, isCompact ? 2 : 3),
          gridMaterial,
        );
        planetGrid.rotation.z = 0.24;
        world.add(planetGrid);

        const atmosphereMaterial = new THREE.MeshBasicMaterial({
          blending: THREE.AdditiveBlending,
          color: 0x62c8ff,
          opacity: 0.1,
          side: THREE.BackSide,
          transparent: true,
        });
        const atmosphere = new THREE.Mesh(
          new THREE.SphereGeometry(1.68, isCompact ? 24 : 48, isCompact ? 16 : 32),
          atmosphereMaterial,
        );
        world.add(atmosphere);

        const orbitMaterials: InstanceType<typeof THREE.LineBasicMaterial>[] = [];
        [
          [2.3, 1.7, 0.28, 0.05],
          [3.15, 2.05, -0.42, 0.38],
          [4.05, 2.55, 0.64, -0.22],
          [5.0, 3.1, -0.24, 0.72],
        ].forEach(([width, height, rotationX, rotationY], index) => {
          const curve = new THREE.EllipseCurve(0, 0, width, height, 0, Math.PI * 2, false, 0);
          const points = curve.getPoints(isCompact ? 80 : 160).map(
            (point) => new THREE.Vector3(point.x, point.y, 0),
          );
          const material = new THREE.LineBasicMaterial({
            blending: THREE.AdditiveBlending,
            color: index === 3 ? 0xffb84d : 0x62c8ff,
            opacity: 0.2,
            transparent: true,
          });
          const orbit = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(points), material);
          orbit.rotation.set(rotationX, rotationY, index * 0.31);
          orbitMaterials.push(material);
          world.add(orbit);
        });

        const beaconMaterial = new THREE.MeshBasicMaterial({
          blending: THREE.AdditiveBlending,
          color: 0x62c8ff,
          opacity: 0.18,
          transparent: true,
        });
        const beaconGeometry = new THREE.OctahedronGeometry(0.07, 0);
        const beacons = new THREE.Group();
        const connectionPositions: number[] = [];
        const beaconCount = isCompact ? 7 : 14;
        for (let index = 0; index < beaconCount; index += 1) {
          const angle = (index / beaconCount) * Math.PI * 2 + random() * 0.35;
          const radius = 2.2 + random() * 3.1;
          const beacon = new THREE.Mesh(beaconGeometry, beaconMaterial);
          beacon.position.set(
            Math.cos(angle) * radius,
            (random() - 0.5) * 3.7,
            Math.sin(angle) * radius * 0.48,
          );
          beacon.scale.setScalar(0.75 + random() * 0.85);
          beacons.add(beacon);
          connectionPositions.push(0, 0, 0, beacon.position.x, beacon.position.y, beacon.position.z);
        }
        world.add(beacons);

        const connectionGeometry = new THREE.BufferGeometry();
        connectionGeometry.setAttribute(
          "position",
          new THREE.Float32BufferAttribute(connectionPositions, 3),
        );
        const connectionMaterial = new THREE.LineBasicMaterial({
          blending: THREE.AdditiveBlending,
          color: 0x62c8ff,
          opacity: 0.06,
          transparent: true,
        });
        const connections = new THREE.LineSegments(connectionGeometry, connectionMaterial);
        world.add(connections);

        const coreMaterial = new THREE.MeshBasicMaterial({
          blending: THREE.AdditiveBlending,
          color: 0xffb84d,
          opacity: 0.95,
          transparent: true,
          wireframe: true,
        });
        const core = new THREE.Mesh(new THREE.OctahedronGeometry(0.24, 1), coreMaterial);
        core.position.set(0, 0, 1.95);
        world.add(core);

        const ambient = new THREE.AmbientLight(0x28485f, 1.15);
        const keyLight = new THREE.DirectionalLight(0x8ad9ff, 3.8);
        keyLight.position.set(-4, 4, 7);
        const rimLight = new THREE.PointLight(0xff8b54, 24, 18, 2);
        rimLight.position.set(4, -2, -3);
        scene.add(ambient, keyLight, rimLight);

        const currentAccent = new THREE.Color(sceneTargets[0].accent);
        const targetAccent = new THREE.Color(sceneTargets[0].accent);
        const currentPosition = new THREE.Vector3(...sceneTargets[0].position);
        const targetPosition = new THREE.Vector3(...sceneTargets[0].position);
        const currentCamera = new THREE.Vector3(...sceneTargets[0].camera);
        const targetCamera = new THREE.Vector3(...sceneTargets[0].camera);
        const lookAt = new THREE.Vector3();

        const resize = () => {
          const width = canvas.clientWidth || window.innerWidth;
          const height = canvas.clientHeight || window.innerHeight;
          const pixelRatioLimit = width <= 768 ? 1.25 : 1.5;
          renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, pixelRatioLimit));
          renderer.setSize(width, height, false);
          camera.aspect = width / Math.max(height, 1);
          camera.updateProjectionMatrix();
          renderStaticRef.current?.();
        };

        const updateWorld = (delta: number, immediate = false) => {
          const target = sceneTargets[Math.min(Math.max(activeSceneRef.current, 0), 3)];
          const blend = immediate ? 1 : 1 - Math.exp(-delta * 3.6);
          targetPosition.set(target.position[0], target.position[1], target.position[2]);
          targetCamera.set(target.camera[0], target.camera[1], target.camera[2]);
          targetAccent.setHex(target.accent);

          currentPosition.lerp(targetPosition, blend);
          currentCamera.lerp(targetCamera, blend);
          currentAccent.lerp(targetAccent, blend);
          world.position.copy(currentPosition);
          world.rotation.x += (target.rotation[0] - world.rotation.x) * blend;
          world.rotation.y += (target.rotation[1] - world.rotation.y) * blend;
          world.rotation.z += (target.rotation[2] - world.rotation.z) * blend;

          const pointer = reducedMotionRef.current ? { x: 0, y: 0 } : pointerRef.current;
          camera.position.set(
            currentCamera.x + pointer.x * 0.24,
            currentCamera.y - pointer.y * 0.16,
            currentCamera.z,
          );
          lookAt.set(currentPosition.x * 0.14, currentPosition.y * 0.12, 0);
          camera.lookAt(lookAt);

          beaconMaterial.opacity += (target.beaconOpacity - beaconMaterial.opacity) * blend;
          connectionMaterial.opacity += (target.beaconOpacity * 0.12 - connectionMaterial.opacity) * blend;
          orbitMaterials.forEach((material, index) => {
            const offset = index === activeSceneRef.current ? 0.14 : 0;
            material.opacity += (target.orbitOpacity + offset - material.opacity) * blend;
          });
          core.scale.lerp(
            new THREE.Vector3(target.coreScale, target.coreScale, target.coreScale),
            blend,
          );
          coreMaterial.color.lerp(currentAccent, blend);
          gridMaterial.color.lerp(currentAccent, blend * 0.7);
          atmosphereMaterial.color.lerp(currentAccent, blend * 0.45);
          beaconMaterial.color.lerp(currentAccent, blend * 0.6);
          connectionMaterial.color.lerp(currentAccent, blend * 0.5);
        };

        const renderStatic = () => {
          if (!reducedMotionRef.current || disposed) return;
          updateWorld(1, true);
          renderer.render(scene, camera);
        };
        renderStaticRef.current = renderStatic;

        const animate = (now: number) => {
          if (disposed || document.hidden || reducedMotionRef.current) return;
          const delta = Math.min((now - lastFrame) / 1000, 0.05);
          lastFrame = now;
          updateWorld(delta);
          const elapsed = now * 0.001;
          stars.rotation.y = elapsed * 0.006;
          planet.rotation.y += delta * 0.035;
          planetGrid.rotation.y -= delta * 0.022;
          core.rotation.x += delta * 0.45;
          core.rotation.y -= delta * 0.62;
          beacons.rotation.y = Math.sin(elapsed * 0.16) * 0.09;
          renderer.render(scene, camera);
          animationFrame = window.requestAnimationFrame(animate);
        };

        const start = () => {
          window.cancelAnimationFrame(animationFrame);
          lastFrame = window.performance.now();
          if (reducedMotionRef.current) renderStatic();
          else if (!document.hidden) animationFrame = window.requestAnimationFrame(animate);
        };

        const onVisibilityChange = () => {
          if (document.hidden) window.cancelAnimationFrame(animationFrame);
          else start();
        };

        const resizeObserver = new ResizeObserver(resize);
        resizeObserver.observe(canvas);
        window.addEventListener("resize", resize);
        document.addEventListener("visibilitychange", onVisibilityChange);
        const removeRuntimeListeners = () => {
          resizeObserver.disconnect();
          window.removeEventListener("resize", resize);
          document.removeEventListener("visibilitychange", onVisibilityChange);
        };

        resize();
        start();

        const dispose = () => {
          window.cancelAnimationFrame(animationFrame);
          renderStaticRef.current = null;
          removeRuntimeListeners?.();
          scene.traverse((object) => {
            if ("geometry" in object && object.geometry instanceof THREE.BufferGeometry) {
              object.geometry.dispose();
            }
            if ("material" in object) {
              const material = object.material as
                | InstanceType<typeof THREE.Material>
                | InstanceType<typeof THREE.Material>[];
              (Array.isArray(material) ? material : [material]).forEach((entry) => entry.dispose());
            }
          });
          renderer.renderLists.dispose();
          renderer.dispose();
          renderer.forceContextLoss();
        };
        teardownRuntime = dispose;
      } catch (error) {
        if (process.env.NODE_ENV !== "production") {
          console.warn("OrbitalWorld enhancement unavailable; using CSS fallback.", error);
        }
      }
    };

    void initialize();
    return () => {
      disposed = true;
      window.cancelAnimationFrame(animationFrame);
      renderStaticRef.current = null;
      teardownRuntime?.();
    };
  }, [pointerRef]);

  return <canvas aria-hidden="true" className="orbital-world" ref={canvasRef} tabIndex={-1} />;
}

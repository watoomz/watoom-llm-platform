#include "WatooMAbilities.h"
#include "WatooMAttributeSet.h"
#include "WatooMCombatCharacter.h"
#include "WatooMCombatData.h"
#include "WatooMCombatTags.h"
#include "WatooMEffects.h"
#include "WatooMProjectile.h"
#include "AbilitySystemBlueprintLibrary.h"
#include "AbilitySystemComponent.h"
#include "Abilities/Tasks/AbilityTask_PlayMontageAndWait.h"
#include "Abilities/Tasks/AbilityTask_WaitGameplayEvent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Camera/CameraShakeBase.h"
#include "Engine/OverlapResult.h"
#include "Engine/StaticMesh.h"
#include "GameFramework/Character.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/KismetMathLibrary.h"
#include "TimerManager.h"

// ---------------------------------------------------------------- base

UWatooMGameplayAbility::UWatooMGameplayAbility()
{
	InstancingPolicy = EGameplayAbilityInstancingPolicy::InstancedPerActor;
	NetExecutionPolicy = EGameplayAbilityNetExecutionPolicy::LocalPredicted;
	ActivationBlockedTags.AddTag(WatooMTags::State_Dead);
	ActivationBlockedTags.AddTag(WatooMTags::State_Stunned);
}

AWatooMCombatCharacter* UWatooMGameplayAbility::GetCombatCharacter() const
{
	return Cast<AWatooMCombatCharacter>(GetAvatarActorFromActorInfo());
}

bool UWatooMGameplayAbility::IsServer() const
{
	const AActor* A = GetAvatarActorFromActorInfo();
	return A && A->HasAuthority();
}

bool UWatooMGameplayAbility::CheckCost(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, FGameplayTagContainer* OptionalRelevantTags) const
{
	const UAbilitySystemComponent* ASC = ActorInfo ? ActorInfo->AbilitySystemComponent.Get() : nullptr;
	if (!ASC) { return false; }
	return ASC->GetNumericAttribute(UWatooMAttributeSet::GetStaminaAttribute()) >= GetStaminaCost()
		&& ASC->GetNumericAttribute(UWatooMAttributeSet::GetManaAttribute()) >= GetManaCost()
		&& ASC->GetNumericAttribute(UWatooMAttributeSet::GetAmmoAttribute()) >= GetAmmoCost();
}

void UWatooMGameplayAbility::ApplyCost(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo) const
{
	if (GetStaminaCost() <= 0.f && GetManaCost() <= 0.f && GetAmmoCost() <= 0.f) { return; }
	FGameplayEffectSpecHandle Spec = MakeOutgoingGameplayEffectSpec(Handle, ActorInfo, ActivationInfo, UWatooMGE_Cost::StaticClass(), GetAbilityLevel(Handle, ActorInfo));
	if (!Spec.IsValid()) { return; }
	Spec.Data->SetSetByCallerMagnitude(WatooMTags::SetByCaller_Stamina, -GetStaminaCost());
	Spec.Data->SetSetByCallerMagnitude(WatooMTags::SetByCaller_Mana, -GetManaCost());
	Spec.Data->SetSetByCallerMagnitude(WatooMTags::SetByCaller_Ammo, -GetAmmoCost());
	ApplyGameplayEffectSpecToOwner(Handle, ActorInfo, ActivationInfo, Spec);
}

const FGameplayTagContainer* UWatooMGameplayAbility::GetCooldownTags() const
{
	CooldownTagsScratch.Reset();
	const FGameplayTag Tag = GetCooldownTag();
	if (Tag.IsValid() && GetCooldownSeconds() > 0.f) { CooldownTagsScratch.AddTag(Tag); }
	return &CooldownTagsScratch;
}

void UWatooMGameplayAbility::ApplyCooldown(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo) const
{
	const FGameplayTag Tag = GetCooldownTag();
	const float Seconds = GetCooldownSeconds();
	if (!Tag.IsValid() || Seconds <= 0.f) { return; }
	FGameplayEffectSpecHandle Spec = MakeOutgoingGameplayEffectSpec(Handle, ActorInfo, ActivationInfo, UWatooMGE_Cooldown::StaticClass(), GetAbilityLevel(Handle, ActorInfo));
	if (!Spec.IsValid()) { return; }
	Spec.Data->SetSetByCallerMagnitude(WatooMTags::SetByCaller_Duration, Seconds);
	Spec.Data->DynamicGrantedTags.AddTag(Tag);
	ApplyGameplayEffectSpecToOwner(Handle, ActorInfo, ActivationInfo, Spec);
}

bool UWatooMGameplayAbility::ApplyDamage(AActor* Target, float Damage, float Multiplier, const FGameplayTag& DamageType) const
{
	UAbilitySystemComponent* Source = GetAbilitySystemComponentFromActorInfo();
	UAbilitySystemComponent* TargetASC = UAbilitySystemBlueprintLibrary::GetAbilitySystemComponent(Target);
	if (!Source || !TargetASC || !Source->IsOwnerActorAuthoritative()) { return false; }
	FGameplayEffectContextHandle Ctx = Source->MakeEffectContext();
	Ctx.AddSourceObject(this);
	Ctx.AddInstigator(GetAvatarActorFromActorInfo(), GetAvatarActorFromActorInfo());
	FGameplayEffectSpecHandle Spec = Source->MakeOutgoingSpec(UWatooMGE_Damage::StaticClass(), 1.f, Ctx);
	Spec.Data->SetSetByCallerMagnitude(WatooMTags::SetByCaller_Damage, Damage);
	Spec.Data->SetSetByCallerMagnitude(WatooMTags::SetByCaller_DamageMultiplier, Multiplier);
	Spec.Data->AddDynamicAssetTag(DamageType.IsValid() ? DamageType : FGameplayTag(WatooMTags::Damage_Type_Physical));
	Source->ApplyGameplayEffectSpecToTarget(*Spec.Data.Get(), TargetASC);
	return true;
}

bool UWatooMGameplayAbility::ApplyHealing(AActor* Target, float Amount) const
{
	UAbilitySystemComponent* Source = GetAbilitySystemComponentFromActorInfo();
	UAbilitySystemComponent* TargetASC = UAbilitySystemBlueprintLibrary::GetAbilitySystemComponent(Target);
	if (!Source || !TargetASC || Amount <= 0.f || !Source->IsOwnerActorAuthoritative()) { return false; }
	FGameplayEffectSpecHandle Spec = Source->MakeOutgoingSpec(UWatooMGE_Heal::StaticClass(), 1.f, Source->MakeEffectContext());
	Spec.Data->SetSetByCallerMagnitude(WatooMTags::SetByCaller_Healing, Amount);
	Source->ApplyGameplayEffectSpecToTarget(*Spec.Data.Get(), TargetASC);
	return true;
}

bool UWatooMGameplayAbility::ApplyEffectClass(AActor* Target, TSubclassOf<UGameplayEffect> Effect) const
{
	UAbilitySystemComponent* Source = GetAbilitySystemComponentFromActorInfo();
	UAbilitySystemComponent* TargetASC = UAbilitySystemBlueprintLibrary::GetAbilitySystemComponent(Target);
	if (!Source || !TargetASC || !Effect || !Source->IsOwnerActorAuthoritative()) { return false; }
	FGameplayEffectSpecHandle Spec = Source->MakeOutgoingSpec(Effect, 1.f, Source->MakeEffectContext());
	Source->ApplyGameplayEffectSpecToTarget(*Spec.Data.Get(), TargetASC);
	return true;
}

void UWatooMGameplayAbility::PlayMontage(UAnimMontage* Montage, bool bEndOnFinish)
{
	if (!Montage) { return; }
	UAbilityTask_PlayMontageAndWait* Task = UAbilityTask_PlayMontageAndWait::CreatePlayMontageAndWaitProxy(this, NAME_None, Montage);
	if (bEndOnFinish)
	{
		Task->OnCompleted.AddDynamic(this, &UWatooMGameplayAbility::OnMontageFinished);
		Task->OnBlendOut.AddDynamic(this, &UWatooMGameplayAbility::OnMontageFinished);
		Task->OnInterrupted.AddDynamic(this, &UWatooMGameplayAbility::OnMontageFinished);
		Task->OnCancelled.AddDynamic(this, &UWatooMGameplayAbility::OnMontageFinished);
	}
	Task->ReadyForActivation();
}

void UWatooMGameplayAbility::OnMontageFinished() { EndNow(); }

void UWatooMGameplayAbility::EndNow()
{
	if (IsActive()) { EndAbility(GetCurrentAbilitySpecHandle(), GetCurrentActorInfo(), GetCurrentActivationInfo(), true, false); }
}

// ---------------------------------------------------------------- melee

UWatooMGA_Melee::UWatooMGA_Melee()
{
	SetAssetTags(FGameplayTagContainer(WatooMTags::Ability_Melee));
}

bool UWatooMGA_Melee::CanActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayTagContainer* SourceTags, const FGameplayTagContainer* TargetTags, FGameplayTagContainer* OptionalRelevantTags) const
{
	const AWatooMCombatCharacter* C = ActorInfo ? Cast<AWatooMCombatCharacter>(ActorInfo->AvatarActor.Get()) : nullptr;
	const UWatooMWeaponData* W = C ? C->GetEquippedWeapon() : nullptr;
	return W && W->Kind == EWatooMWeaponKind::Melee && Super::CanActivateAbility(Handle, ActorInfo, SourceTags, TargetTags, OptionalRelevantTags);
}

float UWatooMGA_Melee::GetStaminaCost() const { const AWatooMCombatCharacter* C = GetCombatCharacter(); const UWatooMWeaponData* W = C ? C->GetEquippedWeapon() : nullptr; return W ? W->StaminaCost : 0.f; }
float UWatooMGA_Melee::GetCooldownSeconds() const { const AWatooMCombatCharacter* C = GetCombatCharacter(); const UWatooMWeaponData* W = C ? C->GetEquippedWeapon() : nullptr; return W ? W->Cooldown : 0.f; }
FGameplayTag UWatooMGA_Melee::GetCooldownTag() const { return WatooMTags::Cooldown_Melee; }

void UWatooMGA_Melee::ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData)
{
	AWatooMCombatCharacter* C = GetCombatCharacter();
	Weapon = C ? C->GetEquippedWeapon() : nullptr;
	if (!Weapon.IsValid() || !CommitAbility(Handle, ActorInfo, ActivationInfo)) { EndAbility(Handle, ActorInfo, ActivationInfo, true, true); return; }
	HitThisSwing.Reset();
	bWindowOpen = bWindowEventSeen = false;

	UAbilityTask_WaitGameplayEvent* Open = UAbilityTask_WaitGameplayEvent::WaitGameplayEvent(this, WatooMTags::Event_MeleeWindowOpen, nullptr, false);
	Open->EventReceived.AddDynamic(this, &UWatooMGA_Melee::OnWindowOpen);
	Open->ReadyForActivation();
	UAbilityTask_WaitGameplayEvent* Close = UAbilityTask_WaitGameplayEvent::WaitGameplayEvent(this, WatooMTags::Event_MeleeWindowClose, nullptr, false);
	Close->EventReceived.AddDynamic(this, &UWatooMGA_Melee::OnWindowClose);
	Close->ReadyForActivation();

	// Fallback timing from the data when the montage carries no WatooM melee-window notify.
	FTimerManager& TM = GetWorld()->GetTimerManager();
	TM.SetTimer(OpenTimer, FTimerDelegate::CreateWeakLambda(this, [this]() { if (!bWindowEventSeen) { OpenWindow(); } }), FMath::Max(Weapon->HitWindowStart, 0.01f), false);
	TM.SetTimer(CloseTimer, FTimerDelegate::CreateWeakLambda(this, [this]() { if (!bWindowEventSeen) { CloseWindow(); } }), FMath::Max(Weapon->HitWindowEnd, Weapon->HitWindowStart + 0.02f), false);
	if (Weapon->AttackMontage)
	{
		PlayMontage(Weapon->AttackMontage);
	}
	else
	{
		TM.SetTimer(EndTimer, FTimerDelegate::CreateWeakLambda(this, [this]() { EndNow(); }), Weapon->HitWindowEnd + 0.1f, false);
	}
	if (C && IsServer() && Weapon->AttackFx.Niagara)
	{
		C->MulticastPlayFx(Weapon->AttackFx.Niagara, Weapon->AttackFx.Sound, C->GetActorLocation(), C->GetActorRotation(), Weapon->AttackFx.Scale);
	}
}

void UWatooMGA_Melee::OnWindowOpen(FGameplayEventData Payload) { bWindowEventSeen = true; OpenWindow(); }
void UWatooMGA_Melee::OnWindowClose(FGameplayEventData Payload) { bWindowEventSeen = true; CloseWindow(); }

void UWatooMGA_Melee::BladeSegment(const UMeshComponent* Mesh, FName StartSocket, FName EndSocket, FVector& OutStart, FVector& OutEnd)
{
	if (!Mesh) { OutStart = OutEnd = FVector::ZeroVector; return; }
	if (Mesh->DoesSocketExist(StartSocket) && Mesh->DoesSocketExist(EndSocket))
	{
		OutStart = Mesh->GetSocketLocation(StartSocket);
		OutEnd = Mesh->GetSocketLocation(EndSocket);
		return;
	}
	// No sockets: run along the longest local bounds axis, through the bounds centre.
	const FBoxSphereBounds Local = Mesh->CalcBounds(FTransform::Identity);
	const FVector E = Local.BoxExtent;
	FVector Axis = FVector::XAxisVector * E.X;
	if (E.Y > E.X && E.Y >= E.Z) { Axis = FVector::YAxisVector * E.Y; }
	else if (E.Z > E.X && E.Z > E.Y) { Axis = FVector::ZAxisVector * E.Z; }
	const FTransform& T = Mesh->GetComponentTransform();
	OutStart = T.TransformPosition(Local.Origin - Axis);
	OutEnd = T.TransformPosition(Local.Origin + Axis);
}

void UWatooMGA_Melee::OpenWindow()
{
	if (bWindowOpen || !IsActive()) { return; }
	bWindowOpen = true;
	SweepCount = 0;
	const AWatooMCombatCharacter* C = GetCombatCharacter();
	BladeSegment(C ? C->GetWeaponMeshComponent() : nullptr, Weapon->TraceStartSocket, Weapon->TraceEndSocket, LastStart, LastEnd);
	if (IsServer())
	{
		GetWorld()->GetTimerManager().SetTimer(SweepTimer, FTimerDelegate::CreateWeakLambda(this, [this]() { Sweep(); }), 1.f / 30.f, true);
	}
}

void UWatooMGA_Melee::CloseWindow()
{
	if (!bWindowOpen) { return; }
	Sweep();
	if (SweepCount < MinSweeps && IsServer()) { ReachSweep(); }
	bWindowOpen = false;
	GetWorld()->GetTimerManager().ClearTimer(SweepTimer);
}

void UWatooMGA_Melee::Sweep()
{
	AWatooMCombatCharacter* C = GetCombatCharacter();
	if (!C || !Weapon.IsValid()) { return; }
	++SweepCount;
	FVector S, E;
	BladeSegment(C->GetWeaponMeshComponent(), Weapon->TraceStartSocket, Weapon->TraceEndSocket, S, E);
	// Sweep the blade's tip and hilt from last frame to this frame, plus the blade itself now.
	const FVector Segs[3][2] = { {LastStart, S}, {LastEnd, E}, {S, E} };
	FCollisionQueryParams Q(SCENE_QUERY_STAT(WatooMMelee), false, C);
	const FCollisionShape Shape = FCollisionShape::MakeSphere(Weapon->TraceRadius);
	for (const auto& Seg : Segs)
	{
		TArray<FHitResult> Hits;
		GetWorld()->SweepMultiByChannel(Hits, Seg[0], Seg[1] + FVector(0.f, 0.f, 0.01f), FQuat::Identity, ECC_Pawn, Shape, Q);
		for (const FHitResult& H : Hits)
		{
			AActor* A = H.GetActor();
			if (!A || A == C || HitThisSwing.Contains(A)) { continue; }
			if (ApplyDamage(A, Weapon->Damage, 1.f, Weapon->DamageType))
			{
				HitThisSwing.Add(A);
				C->MulticastPlayFx(Weapon->ImpactFx.Niagara, Weapon->ImpactFx.Sound, H.ImpactPoint, H.ImpactNormal.Rotation(), Weapon->ImpactFx.Scale);
			}
		}
	}
	LastStart = S;
	LastEnd = E;
}

void UWatooMGA_Melee::ReachSweep()
{
	AWatooMCombatCharacter* C = GetCombatCharacter();
	if (!C || !Weapon.IsValid()) { return; }
	FVector S, E;
	BladeSegment(C->GetWeaponMeshComponent(), Weapon->TraceStartSocket, Weapon->TraceEndSocket, S, E);
	const float Reach = C->GetSimpleCollisionRadius() + FVector::Dist(S, E);
	const FVector From = C->GetActorLocation();
	const FVector To = From + C->GetActorForwardVector() * Reach;
	FCollisionQueryParams Q(SCENE_QUERY_STAT(WatooMMeleeReach), false, C);
	TArray<FHitResult> Hits;
	GetWorld()->SweepMultiByChannel(Hits, From, To, FQuat::Identity, ECC_Pawn, FCollisionShape::MakeSphere(Weapon->TraceRadius * 1.5f), Q);
	for (const FHitResult& H : Hits)
	{
		AActor* A = H.GetActor();
		if (!A || A == C || HitThisSwing.Contains(A)) { continue; }
		if (ApplyDamage(A, Weapon->Damage, 1.f, Weapon->DamageType))
		{
			HitThisSwing.Add(A);
			C->MulticastPlayFx(Weapon->ImpactFx.Niagara, Weapon->ImpactFx.Sound, H.ImpactPoint, H.ImpactNormal.Rotation(), Weapon->ImpactFx.Scale);
		}
	}
}

void UWatooMGA_Melee::EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled)
{
	if (UWorld* W = GetWorld())
	{
		W->GetTimerManager().ClearTimer(SweepTimer);
		W->GetTimerManager().ClearTimer(OpenTimer);
		W->GetTimerManager().ClearTimer(CloseTimer);
		W->GetTimerManager().ClearTimer(EndTimer);
	}
	bWindowOpen = false;
	Super::EndAbility(Handle, ActorInfo, ActivationInfo, bReplicateEndAbility, bWasCancelled);
}

// ---------------------------------------------------------------- gun

UWatooMGA_Gun::UWatooMGA_Gun()
{
	SetAssetTags(FGameplayTagContainer(WatooMTags::Ability_Gun));
	ActivationBlockedTags.AddTag(WatooMTags::State_Reloading);
}

bool UWatooMGA_Gun::CanActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayTagContainer* SourceTags, const FGameplayTagContainer* TargetTags, FGameplayTagContainer* OptionalRelevantTags) const
{
	const AWatooMCombatCharacter* C = ActorInfo ? Cast<AWatooMCombatCharacter>(ActorInfo->AvatarActor.Get()) : nullptr;
	const UWatooMWeaponData* W = C ? C->GetEquippedWeapon() : nullptr;
	if (!W || !W->UsesAmmo()) { return false; }
	if (!Super::CanActivateAbility(Handle, ActorInfo, SourceTags, TargetTags, OptionalRelevantTags))
	{
		// Empty magazine: try a reload instead of a dry click.
		UAbilitySystemComponent* ASC = ActorInfo->AbilitySystemComponent.Get();
		if (ASC && ASC->GetNumericAttribute(UWatooMAttributeSet::GetAmmoAttribute()) < 1.f)
		{
			ASC->TryActivateAbilitiesByTag(FGameplayTagContainer(WatooMTags::Ability_Reload));
		}
		return false;
	}
	return true;
}

float UWatooMGA_Gun::GetCooldownSeconds() const { return Weapon.IsValid() ? Weapon->SecondsPerShot() * 0.95f : 0.f; }
FGameplayTag UWatooMGA_Gun::GetCooldownTag() const { return WatooMTags::Cooldown_Gun; }

void UWatooMGA_Gun::ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData)
{
	const AWatooMCombatCharacter* C = GetCombatCharacter();
	Weapon = C ? C->GetEquippedWeapon() : nullptr;
	if (!Weapon.IsValid()) { EndAbility(Handle, ActorInfo, ActivationInfo, true, true); return; }
	bHeld = true;
	ShotsLeft = Weapon->FireMode == EWatooMFireMode::Burst ? FMath::Max(Weapon->BurstCount, 1) : 1;
	FireLoop();
}

void UWatooMGA_Gun::FireLoop()
{
	if (!IsActive() || !Weapon.IsValid()) { return; }
	const bool bAuto = Weapon->FireMode == EWatooMFireMode::Auto;
	if ((bAuto && !bHeld) || (!bAuto && ShotsLeft <= 0)) { EndNow(); return; }
	if (!CommitAbility(GetCurrentAbilitySpecHandle(), GetCurrentActorInfo(), GetCurrentActivationInfo()))
	{
		if (UAbilitySystemComponent* ASC = GetAbilitySystemComponentFromActorInfo();
			ASC && ASC->GetNumericAttribute(UWatooMAttributeSet::GetAmmoAttribute()) < 1.f)
		{
			EndNow();
			ASC->TryActivateAbilitiesByTag(FGameplayTagContainer(WatooMTags::Ability_Reload));
			return;
		}
	}
	else
	{
		FireOnce();
		--ShotsLeft;
	}
	GetWorld()->GetTimerManager().SetTimer(FireTimer, FTimerDelegate::CreateWeakLambda(this, [this]() { FireLoop(); }), Weapon->SecondsPerShot(), false);
}

void UWatooMGA_Gun::FireOnce()
{
	AWatooMCombatCharacter* C = GetCombatCharacter();
	if (!C) { return; }
	if (Weapon->AttackMontage) { C->PlayAnimMontage(Weapon->AttackMontage); }
	if (!IsServer()) { return; }

	FVector Start, Dir;
	C->GetAim(Start, Dir);
	const UMeshComponent* WM = C->GetWeaponMeshComponent();
	const FVector Muzzle = WM && WM->DoesSocketExist(Weapon->MuzzleSocket) ? WM->GetSocketLocation(Weapon->MuzzleSocket) : C->GetPawnViewLocation();
	C->MulticastPlayFx(Weapon->AttackFx.Niagara, Weapon->AttackFx.Sound, Muzzle, Dir.Rotation(), Weapon->AttackFx.Scale);
	if (APlayerController* PC = Cast<APlayerController>(C->GetController()); PC && Weapon->FireCameraShake)
	{
		PC->ClientStartCameraShake(Weapon->FireCameraShake);
	}

	FCollisionQueryParams Q(SCENE_QUERY_STAT(WatooMGun), true, C);
	Q.bReturnPhysicalMaterial = false;
	if (Weapon->Kind == EWatooMWeaponKind::Bow)
	{
		// An arrow: spawned on the server at the bow, aimed where the view ray lands, flies with gravity (AWatooMProjectile).
		FHitResult Aim;
		const FVector Target = GetWorld()->LineTraceSingleByChannel(Aim, Start, Start + Dir * Weapon->Range, Weapon->TraceChannel, Q)
			? Aim.ImpactPoint : Start + Dir * Weapon->Range;
		const FVector From = Muzzle + Dir * 30.f;
		FActorSpawnParameters SP;
		SP.Owner = C;
		SP.Instigator = C;
		SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		const FRotator Rot = UKismetMathLibrary::RandomUnitVectorInConeInDegrees((Target - From).GetSafeNormal(), Weapon->SpreadDegrees).Rotation();
		if (AWatooMProjectile* Arrow = GetWorld()->SpawnActor<AWatooMProjectile>(AWatooMProjectile::StaticClass(), From, Rot, SP))
		{
			Arrow->InitFromWeapon(Weapon.Get(), this);
		}
		return;
	}
	for (int32 P = 0; P < FMath::Max(Weapon->PelletsPerShot, 1); ++P)
	{
		const FVector ShotDir = UKismetMathLibrary::RandomUnitVectorInConeInDegrees(Dir, Weapon->SpreadDegrees);
		const FVector End = Start + ShotDir * Weapon->Range;
		FHitResult Hit;
		const bool bHit = GetWorld()->LineTraceSingleByChannel(Hit, Start, End, Weapon->TraceChannel, Q);
		const FVector HitPoint = bHit ? Hit.ImpactPoint : End;
		C->MulticastTracer(Weapon->TracerFx, Muzzle, HitPoint);
		if (!bHit) { continue; }
		float Mult = Weapon->FalloffMultiplier(Hit.Distance);
		// The trace stops on the capsule, which has no bones: re-trace the same ray against the character's mesh for the bone.
		FName Bone = Hit.BoneName;
		if (const ACharacter* HitChar = Cast<ACharacter>(Hit.GetActor()))
		{
			FHitResult MeshHit;
			if (HitChar->GetMesh() && HitChar->GetMesh()->LineTraceComponent(MeshHit, Start, End, Q)) { Bone = MeshHit.BoneName; }
		}
		if (Bone != NAME_None && Bone.ToString().Contains(Weapon->HeadBone.ToString())) { Mult *= Weapon->HeadshotMultiplier; }
		ApplyDamage(Hit.GetActor(), Weapon->Damage, Mult, Weapon->DamageType);
		C->MulticastPlayFx(Weapon->ImpactFx.Niagara, Weapon->ImpactFx.Sound, Hit.ImpactPoint, Hit.ImpactNormal.Rotation(), Weapon->ImpactFx.Scale);
	}
}

void UWatooMGA_Gun::InputReleased(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo)
{
	bHeld = false;
	Super::InputReleased(Handle, ActorInfo, ActivationInfo);
}

void UWatooMGA_Gun::EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled)
{
	if (UWorld* W = GetWorld()) { W->GetTimerManager().ClearTimer(FireTimer); }
	bHeld = false;
	Super::EndAbility(Handle, ActorInfo, ActivationInfo, bReplicateEndAbility, bWasCancelled);
}

// ---------------------------------------------------------------- reload

UWatooMGA_Reload::UWatooMGA_Reload()
{
	SetAssetTags(FGameplayTagContainer(WatooMTags::Ability_Reload));
	ActivationOwnedTags.AddTag(WatooMTags::State_Reloading);
	ActivationBlockedTags.AddTag(WatooMTags::State_Reloading);
}

bool UWatooMGA_Reload::CanActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayTagContainer* SourceTags, const FGameplayTagContainer* TargetTags, FGameplayTagContainer* OptionalRelevantTags) const
{
	const AWatooMCombatCharacter* C = ActorInfo ? Cast<AWatooMCombatCharacter>(ActorInfo->AvatarActor.Get()) : nullptr;
	const UWatooMWeaponData* W = C ? C->GetEquippedWeapon() : nullptr;
	const UAbilitySystemComponent* ASC = ActorInfo ? ActorInfo->AbilitySystemComponent.Get() : nullptr;
	if (!W || !W->UsesAmmo() || !ASC || C->GetReserveAmmo() <= 0) { return false; }
	if (ASC->GetNumericAttribute(UWatooMAttributeSet::GetAmmoAttribute()) >= W->MagazineSize) { return false; }
	return Super::CanActivateAbility(Handle, ActorInfo, SourceTags, TargetTags, OptionalRelevantTags);
}

void UWatooMGA_Reload::ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData)
{
	const AWatooMCombatCharacter* C = GetCombatCharacter();
	const UWatooMWeaponData* W = C ? C->GetEquippedWeapon() : nullptr;
	if (!W || !CommitAbility(Handle, ActorInfo, ActivationInfo)) { EndAbility(Handle, ActorInfo, ActivationInfo, true, true); return; }
	PlayMontage(W->ReloadMontage, false);
	GetWorld()->GetTimerManager().SetTimer(ReloadTimer, FTimerDelegate::CreateWeakLambda(this, [this]() { Finish(); }), FMath::Max(W->ReloadSeconds, 0.05f), false);
}

void UWatooMGA_Reload::Finish()
{
	if (AWatooMCombatCharacter* C = GetCombatCharacter(); C && IsServer()) { C->ReloadEquipped(); }
	EndNow();
}

// ---------------------------------------------------------------- spell

UWatooMGA_Spell::UWatooMGA_Spell()
{
	SetAssetTags(FGameplayTagContainer(WatooMTags::Ability_Spell));
}

UWatooMSpellData* UWatooMGA_Spell::GetSpell() const { return Cast<UWatooMSpellData>(GetCurrentSourceObject()); }
float UWatooMGA_Spell::GetManaCost() const { const UWatooMSpellData* S = GetSpell(); return S ? S->ManaCost : 0.f; }
float UWatooMGA_Spell::GetCooldownSeconds() const { const UWatooMSpellData* S = GetSpell(); return S ? S->Cooldown : 0.f; }
FGameplayTag UWatooMGA_Spell::GetCooldownTag() const { const UWatooMSpellData* S = GetSpell(); return S ? S->CooldownTag : FGameplayTag(); }

void UWatooMGA_Spell::ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData)
{
	const UWatooMSpellData* S = GetSpell();
	if (!S || !CommitAbility(Handle, ActorInfo, ActivationInfo)) { EndAbility(Handle, ActorInfo, ActivationInfo, true, true); return; }
	bReleased = false;
	AWatooMCombatCharacter* C = GetCombatCharacter();
	if (C && IsServer() && S->CastFx.Niagara)
	{
		const FVector At = C->GetMesh()->DoesSocketExist(S->CastSocket) ? C->GetMesh()->GetSocketLocation(S->CastSocket) : C->GetActorLocation();
		C->MulticastPlayFx(S->CastFx.Niagara, S->CastFx.Sound, At, C->GetActorRotation(), S->CastFx.Scale);
	}
	UAbilityTask_WaitGameplayEvent* Fire = UAbilityTask_WaitGameplayEvent::WaitGameplayEvent(this, WatooMTags::Event_Fire, nullptr, true);
	Fire->EventReceived.AddDynamic(this, &UWatooMGA_Spell::OnReleaseEvent);
	Fire->ReadyForActivation();
	GetWorld()->GetTimerManager().SetTimer(ReleaseTimer, FTimerDelegate::CreateWeakLambda(this, [this]() { Release(); }), FMath::Max(S->ReleaseDelay, 0.01f), false);
	if (S->CastMontage) { PlayMontage(S->CastMontage, false); }
}

void UWatooMGA_Spell::OnReleaseEvent(FGameplayEventData Payload) { Release(); }

void UWatooMGA_Spell::Release()
{
	if (bReleased || !IsActive()) { return; }
	bReleased = true;
	GetWorld()->GetTimerManager().ClearTimer(ReleaseTimer);
	UWatooMSpellData* S = GetSpell();
	AWatooMCombatCharacter* C = GetCombatCharacter();
	if (S && C && IsServer())
	{
		FVector Start, Dir;
		C->GetAim(Start, Dir);
		const FVector Hand = C->GetMesh()->DoesSocketExist(S->CastSocket) ? C->GetMesh()->GetSocketLocation(S->CastSocket) : C->GetPawnViewLocation();
		FCollisionQueryParams Q(SCENE_QUERY_STAT(WatooMSpell), true, C);
		switch (S->Delivery)
		{
		case EWatooMSpellDelivery::Projectile:
		{
			FActorSpawnParameters P;
			P.Owner = C;
			P.Instigator = C;
			P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
			FHitResult Aim;
			const FVector Target = GetWorld()->LineTraceSingleByChannel(Aim, Start, Start + Dir * S->Range, ECC_Pawn, Q) ? Aim.ImpactPoint : Start + Dir * S->Range;
			if (AWatooMProjectile* Proj = GetWorld()->SpawnActor<AWatooMProjectile>(AWatooMProjectile::StaticClass(), Hand, (Target - Hand).Rotation(), P))
			{
				Proj->InitFromSpell(S, this);
			}
			break;
		}
		case EWatooMSpellDelivery::Hitscan:
		{
			FHitResult Hit;
			const bool bHit = GetWorld()->LineTraceSingleByChannel(Hit, Start, Start + Dir * S->Range, ECC_Pawn, Q);
			const FVector End = bHit ? Hit.ImpactPoint : Start + Dir * S->Range;
			C->MulticastTracer(S->ProjectileFx, Hand, End);
			if (bHit) { HitTargetsAt(Hit.ImpactPoint, Hit.GetActor()); }
			break;
		}
		case EWatooMSpellDelivery::Area:
		{
			FHitResult Hit;
			const FVector Point = GetWorld()->LineTraceSingleByChannel(Hit, Start, Start + Dir * S->Range, ECC_Pawn, Q) ? Hit.ImpactPoint : Start + Dir * S->Range;
			HitTargetsAt(Point, nullptr);
			break;
		}
		case EWatooMSpellDelivery::Self:
			HitTargetsAt(C->GetActorLocation(), C);
			break;
		}
	}
	if (!S || !S->CastMontage) { EndNow(); }
	else { GetWorld()->GetTimerManager().SetTimer(ReleaseTimer, FTimerDelegate::CreateWeakLambda(this, [this]() { EndNow(); }), 0.3f, false); }
}

void UWatooMGA_Spell::HitTargetsAt(const FVector& Point, AActor* DirectHit, UWatooMSpellData* SpellOverride)
{
	UWatooMSpellData* S = SpellOverride ? SpellOverride : GetSpell();
	AWatooMCombatCharacter* C = GetCombatCharacter();
	if (!S || !C) { return; }
	C->MulticastPlayFx(S->ImpactFx.Niagara, S->ImpactFx.Sound, Point, FRotator::ZeroRotator, S->ImpactFx.Scale);
	TArray<AActor*> Targets;
	if (S->Radius > 0.f)
	{
		TArray<FOverlapResult> Overlaps;
		FCollisionObjectQueryParams Obj(ECC_Pawn);
		GetWorld()->OverlapMultiByObjectType(Overlaps, Point, FQuat::Identity, Obj, FCollisionShape::MakeSphere(S->Radius));
		for (const FOverlapResult& O : Overlaps) { if (O.GetActor()) { Targets.AddUnique(O.GetActor()); } }
	}
	if (DirectHit) { Targets.AddUnique(DirectHit); }
	for (AActor* T : Targets)
	{
		const bool bSelf = T == C;
		if (S->Damage > 0.f && !bSelf) { ApplyDamage(T, S->Damage, 1.f, S->DamageType); }
		if (S->Healing > 0.f) { ApplyHealing(T, S->Healing); }   // heals allies and self in the area (damage execution keeps teams safe)
		if (S->StatusEffect && !bSelf) { ApplyEffectClass(T, S->StatusEffect); }
	}
}

void UWatooMGA_Spell::EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled)
{
	if (UWorld* W = GetWorld()) { W->GetTimerManager().ClearTimer(ReleaseTimer); }
	Super::EndAbility(Handle, ActorInfo, ActivationInfo, bReplicateEndAbility, bWasCancelled);
}
